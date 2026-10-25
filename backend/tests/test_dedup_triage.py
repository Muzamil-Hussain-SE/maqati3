"""The bulk-upload decision: byte-identical reject, fingerprint candidate, or new.

Ties layers 2 and 3 together behind the two boundaries a real deployment has to cross
(ffmpeg/fpcalc, and the Postgres `entry_fingerprint_lookup` index) -- both stood in for
here by fakes, per WORKFLOW.md: these are genuinely external systems, not the logic
under test. See docs/ARCHITECTURE.md ("Revidiert 2026-10-25") for why this has to
happen synchronously, while the contributor is still on the page.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from masdar.dedup.triage import (
    ExactDuplicate,
    FingerprintCandidate,
    FingerprintCandidates,
    NewUpload,
    triage_upload,
)

from masdar.dedup.fingerprint import FingerprintMatch

AUDIO = Path("/uploads/22ce82f8-d658-495a-ae0c-619be76f7af9.mp4")


class FakeExtractor:
    """One fingerprint per window, derived from the offset -- same convention as
    test_dedup_fingerprint.py's FakeExtractor."""

    def __init__(self, origin_ms: int = 0) -> None:
        self.calls: list[tuple[Path, int, int]] = []

    def extract(self, path: Path, offset_ms: int, duration_ms: int) -> bytes:
        self.calls.append((path, offset_ms, duration_ms))
        return f"audio@{offset_ms}".encode()


class FakeIndex:
    """Stands in for the Postgres `entry_fingerprint_lookup` index and the
    `entry_fingerprint` table it is built from."""

    def __init__(self, windows_by_entry: dict[str, list[bytes]]) -> None:
        self._windows_by_entry = windows_by_entry
        self.lookup_calls: list[Sequence[bytes]] = []

    def entries_sharing_a_window(self, fingerprints: Sequence[bytes]) -> set[str]:
        self.lookup_calls.append(fingerprints)
        wanted = set(fingerprints)
        return {
            entry_id
            for entry_id, windows in self._windows_by_entry.items()
            if wanted & set(windows)
        }

    def windows_of(self, entry_id: str) -> Sequence[bytes]:
        return self._windows_by_entry[entry_id]


def test_a_byte_identical_upload_is_rejected_without_touching_the_fingerprint_layer() -> None:
    extractor = FakeExtractor()
    index = FakeIndex({})
    result = triage_upload(
        AUDIO,
        duration_ms=90_000,
        known_sha256={"deadbeef": "uthaymin-000421"},
        extractor=extractor,
        index=index,
        sha256="deadbeef",
    )
    assert result == ExactDuplicate(entry_id="uthaymin-000421")
    # The whole point of running sha256 first: no ffmpeg/fpcalc cost for a file that is
    # rejected outright, and no query against the corpus either.
    assert extractor.calls == []
    assert index.lookup_calls == []


def test_a_file_sharing_no_window_with_the_corpus_is_new() -> None:
    extractor = FakeExtractor()
    index = FakeIndex({"other-entry": [b"audio@999999"]})
    result = triage_upload(
        AUDIO,
        duration_ms=90_000,
        known_sha256={},
        extractor=extractor,
        index=index,
        sha256="freshhash",
    )
    assert isinstance(result, NewUpload)
    assert result.sha256 == "freshhash"
    assert [f.offset_ms for f in result.fingerprints] == [0, 15_000, 30_000, 45_000, 60_000]


def test_a_file_sharing_a_long_enough_run_with_an_entry_is_a_candidate() -> None:
    # Same windows as the new upload would produce for a 90s clip (offsets 0, 15000,
    # 30000, 45000, 60000): a different recording of the same fatwa, no intro offset.
    existing_windows = [f"audio@{ms}".encode() for ms in (0, 15_000, 30_000, 45_000, 60_000)]
    index = FakeIndex({"uthaymin-000421": existing_windows})
    result = triage_upload(
        AUDIO,
        duration_ms=90_000,
        known_sha256={},
        extractor=FakeExtractor(),
        index=index,
        sha256="freshhash",
    )
    assert isinstance(result, FingerprintCandidates)
    assert result.sha256 == "freshhash"
    assert result.candidates == [
        FingerprintCandidate(
            entry_id="uthaymin-000421",
            match=FingerprintMatch(matched=True, offset_shift=0, run_length=5),
        )
    ]


def test_a_shared_window_that_does_not_reach_the_minimum_run_is_not_a_candidate() -> None:
    # Only one window happens to coincide -- the corpus lookup surfaces the entry as a
    # possibility, but match_fingerprints must still reject it below min_consecutive.
    index = FakeIndex({"unrelated-entry": [b"audio@30000", b"nothing-else-matches"]})
    result = triage_upload(
        AUDIO,
        duration_ms=90_000,
        known_sha256={},
        extractor=FakeExtractor(),
        index=index,
        sha256="freshhash",
    )
    assert isinstance(result, NewUpload)


def test_candidates_from_several_entries_are_sorted_by_match_strength() -> None:
    weak = [b"audio@0", b"audio@15000", b"audio@15000weak"]
    strong = [f"audio@{ms}".encode() for ms in (0, 15_000, 30_000, 45_000, 60_000)]
    index = FakeIndex({"weak-match": weak, "strong-match": strong})
    result = triage_upload(
        AUDIO,
        duration_ms=90_000,
        known_sha256={},
        extractor=FakeExtractor(),
        index=index,
        sha256="freshhash",
    )
    assert isinstance(result, FingerprintCandidates)
    assert [c.entry_id for c in result.candidates] == ["strong-match", "weak-match"]


def test_a_recording_too_short_to_fingerprint_is_new_without_querying_the_index() -> None:
    index = FakeIndex({})
    result = triage_upload(
        AUDIO,
        duration_ms=0,
        known_sha256={},
        extractor=FakeExtractor(),
        index=index,
        sha256="freshhash",
    )
    assert isinstance(result, NewUpload)
    assert result.fingerprints == []
    assert index.lookup_calls == []
