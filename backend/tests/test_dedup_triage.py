"""The bulk-upload decision: byte-identical reject, fingerprint candidate, or new.

Ties layers 2 and 3 together behind the two boundaries a real deployment has to cross
(fpcalc, and the Postgres key index) -- both stood in for here by fakes, per
WORKFLOW.md: these are genuinely external systems, not the logic under test. See
docs/ARCHITECTURE.md ("Revidiert 2026-10-25") for why this has to happen
synchronously, while the contributor is still on the page.
"""

from __future__ import annotations

import random
from collections.abc import Sequence, Set
from pathlib import Path

from maqati3.dedup.fingerprint import ITEM_MS, Fingerprint, index_keys
from maqati3.dedup.triage import (
    ExactDuplicate,
    FingerprintCandidates,
    NewUpload,
    triage_upload,
)

AUDIO = Path("/uploads/22ce82f8-d658-495a-ae0c-619be76f7af9.mp4")


def noise(n: int, seed: int) -> list[int]:
    rng = random.Random(seed)
    return [rng.getrandbits(32) for _ in range(n)]


def reencode(items: list[int], seed: int) -> list[int]:
    rng = random.Random(seed)
    return [
        item ^ sum(1 << bit for bit in range(32) if rng.random() < 0.02) for item in items
    ]


#: Ninety seconds of one recording.
UPLOAD = noise(round(90_000 / ITEM_MS), seed=1)


class FakeExtractor:
    def __init__(self, items: list[int]) -> None:
        self.items = items
        self.calls: list[Path] = []

    def extract(self, path: Path) -> Fingerprint:
        self.calls.append(path)
        return Fingerprint(items=tuple(self.items), duration_ms=round(len(self.items) * ITEM_MS))


class FakeIndex:
    """Stands in for the Postgres key index: an owner is a candidate when it shares at
    least one sampled key, exactly the query the real index runs (with a threshold)."""

    def __init__(self, items_by_owner: dict[str, list[int]]) -> None:
        self._items = items_by_owner
        self.lookups: list[Set[int]] = []

    def candidates(self, keys: Set[int]) -> set[str]:
        self.lookups.append(keys)
        return {owner for owner, items in self._items.items() if keys & index_keys(items)}

    def items_of(self, key: str) -> Sequence[int]:
        return self._items[key]


def triage(extractor: FakeExtractor, index: FakeIndex, known: dict[str, str] | None = None,
           sha256: str = "freshhash") -> object:
    return triage_upload(
        AUDIO, sha256=sha256, known_sha256=known or {}, extractor=extractor, index=index
    )


def test_a_byte_identical_upload_is_rejected_before_any_decoding() -> None:
    extractor = FakeExtractor(UPLOAD)
    index = FakeIndex({})

    result = triage(extractor, index, known={"deadbeef": "uthaymin-000421"}, sha256="deadbeef")

    assert result == ExactDuplicate(entry_id="uthaymin-000421")
    # The point of checking the hash first: no decoding, no query against the corpus.
    assert extractor.calls == []
    assert index.lookups == []


def test_a_file_sharing_nothing_with_the_corpus_is_new() -> None:
    result = triage(FakeExtractor(UPLOAD), FakeIndex({"other": noise(500, seed=2)}))

    assert isinstance(result, NewUpload)
    assert result.sha256 == "freshhash"
    assert result.fingerprint.items == tuple(UPLOAD)


def test_a_reencoded_copy_of_an_entry_is_a_candidate() -> None:
    index = FakeIndex({"uthaymin-000421": reencode(UPLOAD, seed=3)})

    result = triage(FakeExtractor(UPLOAD), index)

    assert isinstance(result, FingerprintCandidates)
    assert [c.entry_id for c in result.candidates] == ["uthaymin-000421"]
    assert result.candidates[0].match.matched is True


def test_an_owner_that_shares_keys_but_does_not_line_up_is_not_a_candidate() -> None:
    # The key lookup only narrows the search; the full comparison still decides. Here
    # the stored recording shares a few items with the upload but is otherwise
    # unrelated, so it is a lookup hit and not a candidate.
    stray = noise(700, seed=4) + UPLOAD[100:104] + noise(700, seed=5)
    result = triage(FakeExtractor(UPLOAD), FakeIndex({"unrelated": stray}))

    assert isinstance(result, NewUpload)


def test_candidates_are_ordered_by_how_much_of_them_agrees() -> None:
    whole = reencode(UPLOAD, seed=6)
    part = reencode(UPLOAD[: round(len(UPLOAD) * 0.6)], seed=7)
    index = FakeIndex({"a-partial-copy": part, "z-whole-copy": whole})

    result = triage(FakeExtractor(UPLOAD), index)

    assert isinstance(result, FingerprintCandidates)
    assert [c.entry_id for c in result.candidates] == ["z-whole-copy", "a-partial-copy"]


def test_a_file_without_any_fingerprint_is_new_without_querying_the_index() -> None:
    index = FakeIndex({})

    result = triage(FakeExtractor([]), index)

    assert isinstance(result, NewUpload)
    assert index.lookups == []
