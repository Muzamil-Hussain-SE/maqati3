"""The bulk-upload route: stage a file, triage it, tell the contributor what it is.

See docs/ARCHITECTURE.md ("Revidiert 2026-10-25") for why this has to answer while the
contributor is still on the page. The route is tested against fakes for every I/O
boundary (disk, ffmpeg/fpcalc, the fingerprint index, the corpus' known hashes) --
WORKFLOW.md: these are genuinely external systems, not the logic under test.
"""

from __future__ import annotations

import io
import random
from collections.abc import Sequence, Set
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
from masdar.dedup.fingerprint import ITEM_MS, Fingerprint, UnreadableMedia, index_keys

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

#: What the fake extractor produces for every upload: 90 s of one recording.
_RNG = random.Random(1)
ITEMS_90S = [_RNG.getrandbits(32) for _ in range(round(90_000 / ITEM_MS))]


class FakeRepository:
    """Returns exactly the entries it was given. Enough for the upload route, which
    only ever resolves a candidate or duplicate entry_id back to its display fields."""

    def __init__(self, entries: Sequence[EntryRow] = ()) -> None:
        self._entries = {entry.id: entry for entry in entries}

    def entry(self, entry_id: str) -> EntryRow | None:
        return self._entries.get(entry_id)


class FakeStore:
    """Stands in for disk: hands back a fixed staged file whatever bytes arrived, so
    the route's logic is tested without real media."""

    def __init__(self, sha256: str = "freshhash", on_disk: dict[Path, Path] | None = None) -> None:
        self.sha256 = sha256
        self.staged: list[str] = []
        self.discarded: list[Path] = []
        self.on_disk = on_disk or {}

    def stage(self, filename: str, stream: BinaryIO) -> StagedUpload:
        self.staged.append(filename)
        return StagedUpload(path=Path(f"/staging/{filename}"), sha256=self.sha256)

    def discard(self, path: Path) -> None:
        self.discarded.append(path)

    def locate(self, path: Path) -> Path | None:
        return self.on_disk.get(path)


class FakeExtractor:
    def __init__(self, unreadable: bool = False) -> None:
        self.unreadable = unreadable

    def extract(self, path: Path) -> Fingerprint:
        if self.unreadable:
            raise UnreadableMedia("Could not find any audio stream in the file")
        return Fingerprint(items=tuple(ITEMS_90S), duration_ms=90_000)


class FakeIndex:
    def __init__(self, items_by_owner: dict[str, list[int]] | None = None) -> None:
        self._items = items_by_owner or {}

    def candidates(self, keys: Set[int]) -> set[str]:
        return {owner for owner, items in self._items.items() if keys & index_keys(items)}

    def items_of(self, key: str) -> Sequence[int]:
        return self._items[key]


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
        fingerprint: Fingerprint,
        candidate_keys: Sequence[str],
    ) -> bool:
        if self.lose_race:
            return False
        self.recorded[sha256] = {
            "original_name": original_name,
            "staged_path": staged_path,
            "duration_ms": fingerprint.duration_ms,
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

    def staged_path(self, sha256: str) -> Path | None:
        recorded = self.recorded.get(sha256)
        return None if recorded is None else Path(str(recorded["staged_path"]))


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
    extractor: FakeExtractor | None = None,
) -> TestClient:
    app = create_app(
        FakeRepository(entries),  # type: ignore[arg-type]
        store=store or FakeStore(),
        extractor=extractor or FakeExtractor(),
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
    client = client_for(entries=[EXISTING], index=FakeIndex({"uthaymin-000421": ITEMS_90S}))

    body = upload(client).json()

    assert body["status"] == "candidates"
    assert [c["entry_id"] for c in body["candidates"]] == ["uthaymin-000421"]
    assert body["candidates"][0]["scholar"]["name_en"] == "Ibn ʿUthaymīn"
    assert body["candidates"][0]["title_ar"] == "حكم المسح على الجوربين"


def test_a_candidate_file_is_kept_so_the_contributor_can_still_choose_it() -> None:
    store = FakeStore()
    client = client_for(
        entries=[EXISTING], store=store, index=FakeIndex({"uthaymin-000421": ITEMS_90S})
    )

    upload(client)

    assert store.discarded == []


def test_a_candidate_that_is_not_public_is_reported_without_revealing_it() -> None:
    # The upload page sits behind an unlisted link, not a login, so it may not reveal
    # more than the public API does -- and that a withheld entry exists is itself
    # information about a scholar. The contributor still learns there is a likely
    # match, so a real duplicate is not waved through; just not which entry it is.
    client = client_for(entries=[HELD_BACK], index=FakeIndex({"uthaymin-000777": ITEMS_90S}))

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


def test_a_new_upload_is_recorded_with_its_duration() -> None:
    submissions = FakeSubmissions()

    upload(client_for(submissions=submissions), filename="whatsapp.mp4")

    assert submissions.recorded["freshhash"] == {
        "original_name": "whatsapp.mp4",
        "staged_path": Path("/staging/whatsapp.mp4"),
        "duration_ms": 90_000,
        "candidate_keys": [],
    }


def test_a_candidate_upload_is_recorded_with_the_keys_it_matched() -> None:
    # Kept despite a match is the first thing an admin looks at, so the match travels
    # with the submission from the moment it is recorded.
    submissions = FakeSubmissions()
    client = client_for(
        entries=[EXISTING],
        index=FakeIndex({"uthaymin-000421": ITEMS_90S}),
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
    client = client_for(index=FakeIndex({submission_key("otherhash"): ITEMS_90S}))

    response = upload(client)

    candidate = response.json()["candidates"][0]
    assert candidate["pending"] is True
    assert candidate["public"] is False
    assert candidate["entry_id"] is None
    assert "otherhash" not in response.text


def test_a_public_entry_match_is_not_marked_pending() -> None:
    client = client_for(entries=[EXISTING], index=FakeIndex({"uthaymin-000421": ITEMS_90S}))

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


def test_a_file_without_readable_audio_is_refused_and_removed() -> None:
    # A photo, a screen recording without sound, a document renamed .mp4: say so plainly
    # instead of filing something nobody can ever transcribe.
    store = FakeStore()
    submissions = FakeSubmissions()
    client = client_for(
        store=store, submissions=submissions, extractor=FakeExtractor(unreadable=True)
    )

    response = upload(client)

    assert response.status_code == 422
    assert response.json()["detail"] == "no_readable_audio"
    assert store.discarded == [Path("/staging/clip.mp4")]
    assert submissions.recorded == {}


# --------------------------------------------------------------- the link is the key


def keyed_client(key: str = "s3cret") -> TestClient:
    app = create_app(
        FakeRepository([]),  # type: ignore[arg-type]
        store=FakeStore(),
        extractor=FakeExtractor(),
        index=FakeIndex(),
        hashes=FakeHashes(),
        submissions=FakeSubmissions(),
        upload_key=key,
    )
    return TestClient(app)


def test_uploading_without_the_links_key_is_refused() -> None:
    # "Unlisted link" hides the page, not the API behind it. Without this anyone who
    # finds the endpoint can fill the disk; the key in the link is what the brothers have.
    response = upload(keyed_client())

    assert response.status_code == 401
    assert response.json()["detail"] == "upload_key_required"


def test_uploading_with_a_wrong_key_is_refused() -> None:
    files = {"file": ("clip.mp4", io.BytesIO(b"bytes"), "video/mp4")}
    response = keyed_client().post(
        "/api/v1/uploads", files=files, headers={"X-Upload-Key": "guess"}
    )

    assert response.status_code == 401


def test_uploading_with_the_key_works() -> None:
    files = {"file": ("clip.mp4", io.BytesIO(b"bytes"), "video/mp4")}
    response = keyed_client().post(
        "/api/v1/uploads", files=files, headers={"X-Upload-Key": "s3cret"}
    )

    assert response.status_code == 200


def test_deciding_without_the_key_is_refused() -> None:
    response = keyed_client().post("/api/v1/uploads/abc/decision", json={"keep": False})

    assert response.status_code == 401


def test_the_public_library_needs_no_key() -> None:
    assert keyed_client().get("/health").status_code == 200


# --------------------------------------------------------------- what the contributor can look at

PUBLIC_WITH_SOURCE = EntryRow(
    id="uthaymin-000500",
    scholar=UTHAYMIN,
    attribution=Attribution.CONFIRMED,
    visibility=Visibility.PUBLIC,
    languages=(EntryLanguageRow(Lang.AR, ReviewState.APPROVED),),
    title_ar="حكم المسح على الجوربين",
    source_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
)


def test_a_pending_match_can_be_previewed_by_its_id() -> None:
    client = client_for(index=FakeIndex({submission_key("otherhash"): ITEMS_90S}))

    candidate = upload(client).json()["candidates"][0]

    assert candidate["preview_id"] == "otherhash"


def test_a_public_match_offers_its_source_link_and_no_preview() -> None:
    client = client_for(
        entries=[PUBLIC_WITH_SOURCE], index=FakeIndex({"uthaymin-000500": ITEMS_90S})
    )

    candidate = upload(client).json()["candidates"][0]

    assert candidate["source_url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert candidate["preview_id"] is None


def test_a_withheld_match_offers_nothing_to_look_at() -> None:
    client = client_for(entries=[HELD_BACK], index=FakeIndex({"uthaymin-000777": ITEMS_90S}))

    candidate = upload(client).json()["candidates"][0]

    assert candidate["preview_id"] is None
    assert candidate["source_url"] is None


def media_client(tmp_path: Path, *, key: str | None = None) -> tuple[TestClient, bytes]:
    video = tmp_path / "staged.mp4"
    data = b"the other brother's clip" * 100
    video.write_bytes(data)
    submissions = FakeSubmissions()
    submissions.recorded["otherhash"] = {"staged_path": Path("/staging/other.mp4")}
    app = create_app(
        FakeRepository([]),  # type: ignore[arg-type]
        store=FakeStore(on_disk={Path("/staging/other.mp4"): video}),
        extractor=FakeExtractor(),
        index=FakeIndex(),
        hashes=FakeHashes(),
        submissions=submissions,
        upload_key=key,
    )
    return TestClient(app), data


def test_a_pending_upload_streams_for_preview(tmp_path: Path) -> None:
    client, data = media_client(tmp_path)

    response = client.get("/api/v1/uploads/otherhash/media")

    assert response.status_code == 200
    assert response.content == data
    assert response.headers["content-type"] == "video/mp4"


def test_preview_supports_seeking(tmp_path: Path) -> None:
    # Browsers fetch video in byte ranges; without them nothing past the start plays.
    client, data = media_client(tmp_path)

    response = client.get("/api/v1/uploads/otherhash/media", headers={"Range": "bytes=10-19"})

    assert response.status_code == 206
    assert response.content == data[10:20]


def test_preview_needs_the_key_but_takes_it_in_the_url(tmp_path: Path) -> None:
    # A <video src> cannot send a header, so this one route also reads ?k=.
    client, _ = media_client(tmp_path, key="s3cret")

    assert client.get("/api/v1/uploads/otherhash/media").status_code == 401
    assert client.get("/api/v1/uploads/otherhash/media?k=guess").status_code == 401
    assert client.get("/api/v1/uploads/otherhash/media?k=s3cret").status_code == 200


def test_preview_of_something_unknown_is_not_found(tmp_path: Path) -> None:
    client, _ = media_client(tmp_path)

    assert client.get("/api/v1/uploads/nothing/media").status_code == 404


def test_preview_of_a_file_the_store_does_not_vouch_for_is_not_found() -> None:
    # The path comes out of the database. The store, not the route, decides whether it
    # is a staged file; anything else is never served.
    submissions = FakeSubmissions()
    submissions.recorded["otherhash"] = {"staged_path": Path("/etc/passwd")}
    app = create_app(
        FakeRepository([]),  # type: ignore[arg-type]
        store=FakeStore(),
        extractor=FakeExtractor(),
        index=FakeIndex(),
        hashes=FakeHashes(),
        submissions=submissions,
    )

    assert TestClient(app).get("/api/v1/uploads/otherhash/media").status_code == 404
