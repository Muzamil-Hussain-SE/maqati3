"""Dedup layer 3: the same recording with a different cut.

See docs/PIPELINE.md section 2, layer 3. Chromaprint is built for music; one print per
file misses the normal case, the same fatwa with a different intro. Overlapping windows
are the point of this module.
"""

from pathlib import Path

import pytest

from masdar.dedup.fingerprint import (
    DEFAULT_HOP_MS,
    FingerprintExtractionError,
    Window,
    fingerprint_recording,
    match_fingerprints,
    plan_windows,
)


def test_windows_overlap_by_the_hop() -> None:
    windows = plan_windows(duration_ms=90_000, window_ms=30_000, hop_ms=15_000)
    assert [w.offset_ms for w in windows] == [0, 15_000, 30_000, 45_000, 60_000]
    assert [w.idx for w in windows] == [0, 1, 2, 3, 4]


def test_a_recording_of_zero_length_gets_no_windows() -> None:
    assert plan_windows(duration_ms=0) == []


def test_a_recording_shorter_than_one_window_gets_exactly_one_window() -> None:
    assert plan_windows(duration_ms=12_000) == [Window(idx=0, offset_ms=0)]


def test_a_recording_exactly_one_window_long_gets_exactly_one_window() -> None:
    assert plan_windows(duration_ms=30_000) == [Window(idx=0, offset_ms=0)]


def test_no_trailing_window_is_planned_once_the_previous_one_reaches_the_end() -> None:
    # 45 s: the window at 15 s already covers to 45 s, so no window starts at 30 s.
    assert [w.offset_ms for w in plan_windows(duration_ms=45_000)] == [0, 15_000]


def test_window_indices_are_contiguous_from_zero() -> None:
    windows = plan_windows(duration_ms=10 * 60_000)
    assert [w.idx for w in windows] == list(range(len(windows)))


def test_offsets_are_strictly_increasing() -> None:
    offsets = [w.offset_ms for w in plan_windows(duration_ms=7 * 60_000)]
    assert all(b > a for a, b in zip(offsets, offsets[1:], strict=False))


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"window_ms": 0}, "window_ms"),
        ({"window_ms": -1}, "window_ms"),
        ({"hop_ms": 0}, "hop_ms"),
        ({"hop_ms": -1}, "hop_ms"),
        ({"window_ms": 10_000, "hop_ms": 20_000}, "overlap"),
        ({"duration_ms": -1}, "duration_ms"),
    ],
)
def test_nonsensical_window_parameters_raise(kwargs: dict[str, int], message: str) -> None:
    call = {"duration_ms": 60_000, **kwargs}
    with pytest.raises(ValueError, match=message):
        plan_windows(**call)


def fp(*values: int) -> list[bytes]:
    """Stand-in window fingerprints. Real ones are Chromaprint bytes; the matcher only
    ever compares them for equality, so distinct small byte strings are faithful."""
    return [bytes([v]) for v in values]


def test_two_unrelated_recordings_do_not_match() -> None:
    result = match_fingerprints(fp(1, 2, 3, 4, 5), fp(90, 91, 92, 93, 94))
    assert result.matched is False
    assert result.offset_shift is None
    assert result.run_length == 0


BARE = fp(10, 11, 12, 13, 14, 15)


def test_the_same_recording_with_an_extra_intro_still_matches() -> None:
    with_intro = fp(90, 91) + BARE
    result = match_fingerprints(BARE, with_intro)
    assert result.matched is True
    assert result.offset_shift == 2
    assert result.run_length == len(BARE)


def test_the_shift_is_negative_when_the_intro_is_on_the_first_recording() -> None:
    with_intro = fp(90, 91) + BARE
    result = match_fingerprints(with_intro, BARE)
    assert result.matched is True
    assert result.offset_shift == -2


def test_an_identical_pair_matches_at_shift_zero() -> None:
    result = match_fingerprints(BARE, BARE)
    assert result.matched is True
    assert result.offset_shift == 0
    assert result.run_length == len(BARE)


def test_a_shorter_cut_of_the_same_recording_matches_on_the_overlap() -> None:
    # b is the middle of a: intro and outro trimmed away.
    result = match_fingerprints(BARE, BARE[2:5])
    assert result.matched is True
    assert result.offset_shift == -2
    assert result.run_length == 3


def test_a_run_shorter_than_min_consecutive_is_reported_but_not_a_match() -> None:
    a = fp(1, 2, 3, 4)
    b = fp(80, 2, 3, 81)
    result = match_fingerprints(a, b, min_consecutive=3)
    assert result.matched is False
    assert result.run_length == 2
    assert result.offset_shift == 0


def test_the_minimum_run_length_is_honoured() -> None:
    a = fp(1, 2, 3, 4)
    b = fp(80, 2, 3, 81)
    assert match_fingerprints(a, b, min_consecutive=2).matched is True


def test_a_single_coincidentally_equal_window_is_not_a_match() -> None:
    result = match_fingerprints(fp(1, 2, 3, 4, 5), fp(70, 71, 3, 72, 73))
    assert result.matched is False
    assert result.run_length == 1


@pytest.mark.parametrize(("a", "b"), [([], []), (BARE, []), ([], BARE)])
def test_an_empty_window_sequence_never_matches(a: list[bytes], b: list[bytes]) -> None:
    result = match_fingerprints(a, b)
    assert result.matched is False
    assert result.offset_shift is None
    assert result.run_length == 0


def test_a_min_consecutive_below_one_is_rejected() -> None:
    with pytest.raises(ValueError, match="min_consecutive"):
        match_fingerprints(BARE, BARE, min_consecutive=0)


def test_the_result_is_the_same_whichever_way_round_the_longest_run_is_measured() -> None:
    with_intro = fp(90, 91) + BARE
    forwards = match_fingerprints(BARE, with_intro)
    backwards = match_fingerprints(with_intro, BARE)
    assert forwards.run_length == backwards.run_length
    assert forwards.offset_shift == -(backwards.offset_shift or 0)


class FakeExtractor:
    """Stands in for Chromaprint. Records how it was called and hands back a fingerprint
    derived from the offset, so a shifted recording produces a shifted window sequence."""

    def __init__(self, empty_at: set[int] | None = None, origin_ms: int = 0) -> None:
        self.calls: list[tuple[Path, int, int]] = []
        self._empty_at = empty_at or set()
        self._origin_ms = origin_ms

    def extract(self, path: Path, offset_ms: int, duration_ms: int) -> bytes:
        self.calls.append((path, offset_ms, duration_ms))
        if offset_ms in self._empty_at:
            return b""
        return f"audio@{self._origin_ms + offset_ms}".encode()


AUDIO = Path("/cold/uthaymin-000421.opus")


def test_a_window_that_yields_no_fingerprint_raises_instead_of_storing_an_empty_one() -> None:
    # An empty fingerprint would compare equal to every other empty one and manufacture
    # duplicates across unrelated entries.
    extractor = FakeExtractor(empty_at={15_000})
    with pytest.raises(FingerprintExtractionError, match="15000"):
        fingerprint_recording(AUDIO, duration_ms=90_000, extractor=extractor)


def test_every_planned_window_is_extracted_and_returned_in_order() -> None:
    extractor = FakeExtractor()
    rows = fingerprint_recording(AUDIO, duration_ms=90_000, extractor=extractor)
    assert [r.window_idx for r in rows] == [0, 1, 2, 3, 4]
    assert [r.offset_ms for r in rows] == [0, 15_000, 30_000, 45_000, 60_000]
    assert all(r.fingerprint for r in rows)


def test_the_last_window_is_clamped_to_the_end_of_the_recording() -> None:
    extractor = FakeExtractor()
    fingerprint_recording(AUDIO, duration_ms=90_000, extractor=extractor)
    assert extractor.calls[0] == (AUDIO, 0, 30_000)
    # The window at 60 s would run to 90 s, which is exactly the end.
    assert extractor.calls[-1] == (AUDIO, 60_000, 30_000)
    short = FakeExtractor()
    fingerprint_recording(AUDIO, duration_ms=70_000, extractor=short)
    assert short.calls[-1] == (AUDIO, 45_000, 25_000)


def test_a_recording_of_zero_length_extracts_nothing() -> None:
    extractor = FakeExtractor()
    assert fingerprint_recording(AUDIO, duration_ms=0, extractor=extractor) == []
    assert extractor.calls == []


def test_a_recording_with_an_intro_matches_the_bare_one_end_to_end() -> None:
    # The whole point of layer 3, exercised through the extractor boundary: the same
    # audio with 30 s of intro glued on. Window 2 of the longer file is window 0 of the
    # shorter one.
    bare = fingerprint_recording(AUDIO, duration_ms=120_000, extractor=FakeExtractor())
    with_intro = fingerprint_recording(
        AUDIO, duration_ms=150_000, extractor=FakeExtractor(origin_ms=-30_000)
    )
    result = match_fingerprints(
        [r.fingerprint for r in bare], [r.fingerprint for r in with_intro]
    )
    assert result.matched is True
    assert result.offset_shift == 2
    assert result.offset_shift * DEFAULT_HOP_MS == 30_000


def test_an_intro_that_is_not_a_multiple_of_the_hop_does_not_match() -> None:
    # Known limit of window matching, pinned on purpose: windows only line up when the
    # shift is a whole number of hops. A 7 s intro moves every window onto different
    # audio, so nothing compares equal. Layer 4 (text) is what catches those.
    bare = fingerprint_recording(AUDIO, duration_ms=120_000, extractor=FakeExtractor())
    with_intro = fingerprint_recording(
        AUDIO, duration_ms=127_000, extractor=FakeExtractor(origin_ms=-7_000)
    )
    result = match_fingerprints(
        [r.fingerprint for r in bare], [r.fingerprint for r in with_intro]
    )
    assert result.matched is False
