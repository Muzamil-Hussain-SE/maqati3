"""The bulk-upload route: stage a file, triage it, tell the contributor what it is.

See docs/ARCHITECTURE.md ("Revidiert 2026-10-25") for why this has to answer while the
contributor is still on the page. The route is tested against fakes for every I/O
boundary (disk, ffmpeg/fpcalc, the fingerprint index, the corpus' known hashes) --
WORKFLOW.md: these are genuinely external systems, not the logic under test.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from pathlib import Path
from typing import BinaryIO

from fastapi.testclient import TestClient
from httpx import Response

from masdar.api.app import create_app
from masdar.api.repository import (
    Attribution,
    EntryLanguageRow,
    EntryRow,
    Lang,
    ReviewState,
    ScholarRef,
    Visibility,
)
from masdar.api.uploads import (
    InvalidMetadata,
    StagedUpload,
    SubmissionMetadata,
    submission_key,
)
from masdar.dedup.fingerprint import WindowFingerprint

UTHAYMIN = ScholarRef(id="ibn-uthaymin", name_ar="ابن عثيمين", name_en="Ibn ʿUthaymīn")

EXISTING = EntryRow(
    id="uthaymin-000421",
    scholar=UTHAYMIN,
    attribution=Attribution.CONFIRMED,
    visibility=Visibility.PUBLIC,
    languages=(EntryLanguageRow(Lang.AR, ReviewState.APPROVED),),
    title_ar="حكم المسح على الجوربين",
)

#: On file, but not public: the public API answers 404 for it, as if it did not exist.
HELD_BACK = EntryRow(
    id="uthaymin-000777",
    scholar=UTHAYMIN,
    attribution=Attribution.CONFIRMED,
    visibility=Visibility.HELD_BACK,
    languages=(EntryLanguageRow(Lang.AR, ReviewState.APPROVED),),
    title_ar="عنوان محجوب",
)

#: What the fake extractor produces for a 90 s upload: one window every 15 s.
WINDOWS_90S = [f"audio@{ms}".encode() for ms in (0, 15_000, 30_000, 45_000, 60_000)]


class FakeRepository:
    """Returns exactly the entries it was given. Enough for the upload route, which
    only ever resolves a candidate or duplicate entry_id back to its display fields."""

    def __init__(self, entries: Sequence[EntryRow] = ()) -> None:
        self._entries = {entry.id: entry for entry in entries}

    def entry(self, entry_id: str) -> EntryRow | None:
        return self._entries.get(entry_id)


class FakeStore:
    """Stands in for disk + ffprobe: hands back a fixed staged file whatever bytes
    arrived, so the route's logic is tested without real media."""

    def __init__(self, sha256: str = "freshhash", duration_ms: int = 90_000) -> None:
        self.sha256 = sha256
        self.duration_ms = duration_ms
        self.staged: list[str] = []
        self.discarded: list[Path] = []

    def stage(self, filename: str, stream: BinaryIO) -> StagedUpload:
        self.staged.append(filename)
        return StagedUpload(
            path=Path(f"/staging/{filename}"),
            sha256=self.sha256,
            duration_ms=self.duration_ms,
        )

    def discard(self, path: Path) -> None:
        self.discarded.append(path)


class FakeExtractor:
    def extract(self, path: Path, offset_ms: int, duration_ms: int) -> bytes:
        return f"audio@{offset_ms}".encode()


class FakeIndex:
    def __init__(self, windows_by_entry: dict[str, list[bytes]] | None = None) -> None:
        self._windows_by_entry = windows_by_entry or {}

    def entries_sharing_a_window(self, fingerprints: Sequence[bytes]) -> set[str]:
        wanted = set(fingerprints)
        return {e for e, windows in self._windows_by_entry.items() if wanted & set(windows)}

    def windows_of(self, entry_id: str) -> Sequence[bytes]:
        return self._windows_by_entry[entry_id]


class FakeSubmissions:
    """Stands in for the submission table. Records what the route asked of it."""

    def __init__(self, *, lose_race: bool = False, unknown_scholar: bool = False) -> None:
        self.lose_race = lose_race
        self.unknown_scholar = unknown_scholar
        self.recorded: dict[str, dict[str, object]] = {}
        self.kept: dict[str, SubmissionMetadata] = {}

    def record(
        self,
        *,
        sha256: str,
        original_name: str,
        staged_path: Path,
        duration_ms: int,
        fingerprints: Sequence[WindowFingerprint],
        candidate_keys: Sequence[str],
    ) -> bool:
        if self.lose_race:
            return False
        self.recorded[sha256] = {
            "original_name": original_name,
            "staged_path": staged_path,
            "windows": len(fingerprints),
            "candidate_keys": list(candidate_keys),
        }
        return True

    def keep(self, sha256: str, metadata: SubmissionMetadata) -> bool:
        if self.unknown_scholar:
            raise InvalidMetadata("unknown scholar")
        if sha256 not in self.recorded or sha256 in self.kept:
            return False
        self.kept[sha256] = metadata
        return True

    def drop(self, sha256: str) -> Path | None:
        if sha256 not in self.recorded or sha256 in self.kept:
            return None
        return Path(str(self.recorded.pop(sha256)["staged_path"]))


class FakeHashes:
    def __init__(self, known: dict[str, str] | None = None) -> None:
        self._known = known or {}

    def known(self) -> dict[str, str]:
        return self._known


def client_for(
    *,
    entries: Sequence[EntryRow] = (),
    store: FakeStore | None = None,
    hashes: FakeHashes | None = None,
    index: FakeIndex | None = None,
    submissions: FakeSubmissions | None = None,
) -> TestClient:
    app = create_app(
        FakeRepository(entries),  # type: ignore[arg-type]
        store=store or FakeStore(),
        extractor=FakeExtractor(),
        index=index or FakeIndex(),
        hashes=hashes or FakeHashes(),
        submissions=submissions or FakeSubmissions(),
    )
    return TestClient(app)


def upload(client: TestClient, filename: str = "clip.mp4") -> Response:
    files = {"file": (filename, io.BytesIO(b"pretend video bytes"), "video/mp4")}
    return client.post("/api/v1/uploads", files=files)


def test_a_file_matching_a_known_hash_is_rejected() -> None:
    client = client_for(
        entries=[EXISTING],
        store=FakeStore(sha256="deadbeef"),
        hashes=FakeHashes({"deadbeef": "uthaymin-000421"}),
    )

    response = upload(client)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert body["sha256"] == "deadbeef"
    assert body["duplicate_of"]["entry_id"] == "uthaymin-000421"
    assert body["duplicate_of"]["scholar"]["name_en"] == "Ibn ʿUthaymīn"


def test_a_rejected_file_is_discarded_from_staging() -> None:
    store = FakeStore(sha256="deadbeef")
    client = client_for(
        entries=[EXISTING], store=store, hashes=FakeHashes({"deadbeef": "uthaymin-000421"})
    )

    upload(client)

    assert store.discarded == [Path("/staging/clip.mp4")]


def test_a_file_with_no_hash_or_fingerprint_match_is_new() -> None:
    body = upload(client_for(store=FakeStore(sha256="freshhash"))).json()

    assert body["status"] == "new"
    assert body["sha256"] == "freshhash"
    assert body["duplicate_of"] is None
    assert body["candidates"] == []


def test_a_new_file_is_kept_in_staging() -> None:
    store = FakeStore()

    upload(client_for(store=store))

    assert store.discarded == []


def test_a_file_sharing_a_long_run_with_an_entry_lists_it_as_a_candidate() -> None:
    client = client_for(entries=[EXISTING], index=FakeIndex({"uthaymin-000421": WINDOWS_90S}))

    body = upload(client).json()

    assert body["status"] == "candidates"
    assert [c["entry_id"] for c in body["candidates"]] == ["uthaymin-000421"]
    assert body["candidates"][0]["scholar"]["name_en"] == "Ibn ʿUthaymīn"
    assert body["candidates"][0]["title_ar"] == "حكم المسح على الجوربين"


def test_a_candidate_file_is_kept_so_the_contributor_can_still_choose_it() -> None:
    store = FakeStore()
    client = client_for(
        entries=[EXISTING], store=store, index=FakeIndex({"uthaymin-000421": WINDOWS_90S})
    )

    upload(client)

    assert store.discarded == []


def test_a_candidate_that_is_not_public_is_reported_without_revealing_it() -> None:
    # The upload page sits behind an unlisted link, not a login, so it may not reveal
    # more than the public API does -- and that a withheld entry exists is itself
    # information about a scholar. The contributor still learns there is a likely
    # match, so a real duplicate is not waved through; just not which entry it is.
    client = client_for(entries=[HELD_BACK], index=FakeIndex({"uthaymin-000777": WINDOWS_90S}))

    response = upload(client)

    candidate = response.json()["candidates"][0]
    assert candidate["public"] is False
    assert candidate["entry_id"] is None
    assert candidate["scholar"] is None
    assert candidate["title_ar"] is None
    assert "uthaymin-000777" not in response.text
    assert "عنوان محجوب" not in response.text


def test_an_exact_duplicate_of_a_non_public_entry_is_rejected_without_revealing_it() -> None:
    client = client_for(
        entries=[HELD_BACK],
        store=FakeStore(sha256="deadbeef"),
        hashes=FakeHashes({"deadbeef": "uthaymin-000777"}),
    )

    response = upload(client)

    body = response.json()
    assert body["status"] == "rejected"
    assert body["duplicate_of"]["public"] is False
    assert body["duplicate_of"]["entry_id"] is None
    assert "uthaymin-000777" not in response.text


def test_uploading_without_a_file_is_a_client_error() -> None:
    response = client_for().post("/api/v1/uploads")

    assert response.status_code == 422


# --------------------------------------------------------------- recording


def test_a_new_upload_is_recorded_with_its_windows() -> None:
    submissions = FakeSubmissions()

    upload(client_for(submissions=submissions), filename="whatsapp.mp4")

    assert submissions.recorded["freshhash"] == {
        "original_name": "whatsapp.mp4",
        "staged_path": Path("/staging/whatsapp.mp4"),
        "windows": 5,
        "candidate_keys": [],
    }


def test_a_candidate_upload_is_recorded_with_the_keys_it_matched() -> None:
    # Kept despite a match is the first thing an admin looks at, so the match travels
    # with the submission from the moment it is recorded.
    submissions = FakeSubmissions()
    client = client_for(
        entries=[EXISTING],
        index=FakeIndex({"uthaymin-000421": WINDOWS_90S}),
        submissions=submissions,
    )

    upload(client)

    assert submissions.recorded["freshhash"]["candidate_keys"] == ["uthaymin-000421"]


def test_a_rejected_upload_is_not_recorded() -> None:
    submissions = FakeSubmissions()
    client = client_for(
        entries=[EXISTING],
        store=FakeStore(sha256="deadbeef"),
        hashes=FakeHashes({"deadbeef": "uthaymin-000421"}),
        submissions=submissions,
    )

    upload(client)

    assert submissions.recorded == {}


def test_losing_the_race_to_an_identical_upload_is_a_rejection() -> None:
    # Two brothers upload the same clip at the same moment; the other one was first.
    store = FakeStore()
    client = client_for(store=store, submissions=FakeSubmissions(lose_race=True))

    body = upload(client).json()

    assert body["status"] == "rejected"
    assert body["duplicate_of"]["pending"] is True
    assert store.discarded == [Path("/staging/clip.mp4")]


def test_a_match_on_a_pending_upload_says_so_without_naming_it() -> None:
    client = client_for(index=FakeIndex({submission_key("otherhash"): WINDOWS_90S}))

    response = upload(client)

    candidate = response.json()["candidates"][0]
    assert candidate["pending"] is True
    assert candidate["public"] is False
    assert candidate["entry_id"] is None
    assert "otherhash" not in response.text


def test_a_public_entry_match_is_not_marked_pending() -> None:
    client = client_for(entries=[EXISTING], index=FakeIndex({"uthaymin-000421": WINDOWS_90S}))

    assert upload(client).json()["candidates"][0]["pending"] is False


# --------------------------------------------------------------- the contributor decides

KEEP = {
    "keep": True,
    "contributor": "Abdullah",
    "scholar_id": "ibn-uthaymin",
    "claimed_attribution": "probably",
    "source_note": "from the Uthaymin WhatsApp group",
}


def decide(client: TestClient, body: dict[str, object], sha256: str = "freshhash") -> Response:
    return client.post(f"/api/v1/uploads/{sha256}/decision", json=body)


def test_keeping_an_upload_stores_what_the_contributor_said() -> None:
    submissions = FakeSubmissions()
    client = client_for(submissions=submissions)
    upload(client)

    response = decide(client, KEEP)

    assert response.status_code == 200
    assert response.json() == {"sha256": "freshhash", "status": "kept"}
    assert submissions.kept["freshhash"] == SubmissionMetadata(
        contributor="Abdullah",
        scholar_id="ibn-uthaymin",
        scholar_other=None,
        topic_id=None,
        claimed_attribution=Attribution.PROBABLY,
        source_note="from the Uthaymin WhatsApp group",
        note=None,
    )


def test_keeping_needs_to_know_whose_words_these_are() -> None:
    client = client_for()
    upload(client)

    response = decide(client, {**KEEP, "scholar_id": None, "scholar_other": "   "})

    assert response.status_code == 422


def test_a_scholar_not_in_the_list_can_be_named_freely() -> None:
    submissions = FakeSubmissions()
    client = client_for(submissions=submissions)
    upload(client)

    response = decide(client, {**KEEP, "scholar_id": None, "scholar_other": "Shaykh Rabi"})

    assert response.status_code == 200
    assert submissions.kept["freshhash"].scholar_other == "Shaykh Rabi"


def test_keeping_needs_the_contributors_confidence() -> None:
    client = client_for()
    upload(client)

    body = {key: value for key, value in KEEP.items() if key != "claimed_attribution"}

    assert decide(client, body).status_code == 422


def test_keeping_with_a_scholar_or_topic_the_database_does_not_know_is_refused() -> None:
    client = client_for(submissions=FakeSubmissions(unknown_scholar=True))
    upload(client)

    response = decide(client, KEEP)

    assert response.status_code == 422
    assert response.json()["detail"] == "unknown_scholar_or_topic"


def test_deciding_twice_is_refused() -> None:
    client = client_for()
    upload(client)
    decide(client, KEEP)

    response = decide(client, KEEP)

    assert response.status_code == 409
    assert response.json()["detail"] == "not_awaiting_decision"


def test_dropping_an_upload_removes_its_staged_file() -> None:
    store = FakeStore()
    client = client_for(store=store)
    upload(client)

    response = decide(client, {"keep": False})

    assert response.status_code == 200
    assert response.json() == {"sha256": "freshhash", "status": "dropped"}
    assert store.discarded == [Path("/staging/clip.mp4")]


def test_dropping_needs_no_metadata() -> None:
    client = client_for()
    upload(client)

    assert decide(client, {"keep": False}).status_code == 200


def test_dropping_something_that_is_not_pending_touches_no_file() -> None:
    store = FakeStore()
    client = client_for(store=store)

    response = decide(client, {"keep": False}, sha256="neveruploaded")

    assert response.status_code == 409
    assert store.discarded == []
