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
from masdar.api.uploads import StagedUpload

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
) -> TestClient:
    app = create_app(
        FakeRepository(entries),  # type: ignore[arg-type]
        store=store or FakeStore(),
        extractor=FakeExtractor(),
        index=index or FakeIndex(),
        hashes=hashes or FakeHashes(),
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
