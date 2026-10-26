"""Dedup layer 3: the same recording, re-encoded, re-cut, or with something glued on.

See docs/PIPELINE.md section 2, layer 3. A forwarded clip is always re-encoded, and a
re-encoded Chromaprint fingerprint is never byte-identical to the original -- measured
on real audio, 1-9 % of its bits differ (unrelated speech: ~48 %), and roughly half of
its 32-bit items survive exactly. So recordings are aligned by voting on the items
that survive, and confirmed by the bit error rate where they agree.

The fixtures model exactly that: `reencode` flips 2 % of the bits at random, which
leaves about half of the items intact, as the real measurement did.
"""

from __future__ import annotations

import random

import pytest

from maqati3.dedup.fingerprint import (
    ITEM_MS,
    decode_items,
    encode_items,
    index_keys,
    match_fingerprints,
)


def noise(n: int, seed: int) -> list[int]:
    """Unrelated audio: independent random items."""
    rng = random.Random(seed)
    return [rng.getrandbits(32) for _ in range(n)]


def reencode(items: list[int], seed: int, bit_flip_rate: float = 0.02) -> list[int]:
    rng = random.Random(seed)
    out = []
    for item in items:
        for bit in range(32):
            if rng.random() < bit_flip_rate:
                item ^= 1 << bit
        out.append(item)
    return out


def seconds(s: float) -> int:
    """How many items cover `s` seconds of audio."""
    return round(s * 1000 / ITEM_MS)


FATWA = noise(seconds(180), seed=1)  # a three-minute fatwa


def test_an_identical_fingerprint_matches_at_offset_zero() -> None:
    result = match_fingerprints(FATWA, FATWA)
    assert result.matched is True
    assert result.offset_ms == 0
    assert result.bit_error_rate == 0.0


def test_a_reencoded_copy_matches() -> None:
    # The case the old exact-equality comparison could never catch.
    result = match_fingerprints(FATWA, reencode(FATWA, seed=2))
    assert result.matched is True
    assert result.offset_ms == 0
    assert result.bit_error_rate is not None
    assert result.bit_error_rate < 0.05


def test_an_unrelated_recording_does_not_match() -> None:
    result = match_fingerprints(FATWA, noise(seconds(180), seed=3))
    assert result.matched is False
    assert result.offset_ms is None


def test_an_intro_of_any_length_is_found_and_measured() -> None:
    # 7 s of something else in front: not a multiple of any hop, which the old window
    # scheme could never line up.
    intro = noise(seconds(7), seed=4)
    result = match_fingerprints(FATWA, reencode(intro + FATWA, seed=5))
    assert result.matched is True
    assert result.offset_ms == round(len(intro) * ITEM_MS)


def test_a_cut_out_of_the_middle_matches_with_a_negative_offset() -> None:
    cut = FATWA[seconds(30) : seconds(70)]
    result = match_fingerprints(FATWA, reencode(cut, seed=6))
    assert result.matched is True
    assert result.offset_ms == -round(seconds(30) * ITEM_MS)


def test_a_clip_holding_this_fatwa_and_another_still_matches() -> None:
    # A forwarded compilation: the fatwa on file, then a different one. Averaged over
    # the whole aligned stretch the second half would drown the first; the match is
    # judged on the longest stretch that agrees.
    compilation = reencode(FATWA + noise(seconds(180), seed=7), seed=8)
    result = match_fingerprints(FATWA, compilation)
    assert result.matched is True
    assert result.overlap_ms >= round(seconds(170) * ITEM_MS)


def test_a_shared_programme_intro_alone_is_not_a_match() -> None:
    # Every episode of a radio programme opens with the same jingle. Two different
    # fatawa from it must not be offered as duplicates of each other.
    jingle = noise(seconds(15), seed=9)
    episode_a = jingle + FATWA
    episode_b = reencode(jingle + noise(seconds(180), seed=10), seed=11)
    result = match_fingerprints(episode_a, episode_b)
    assert result.matched is False


def test_an_agreeing_stretch_shorter_than_ten_seconds_is_not_a_match() -> None:
    snippet = FATWA[: seconds(6)]
    result = match_fingerprints(FATWA, reencode(snippet, seed=12))
    assert result.matched is False


@pytest.mark.parametrize(("a", "b"), [([], []), (FATWA, []), ([], FATWA)])
def test_an_empty_fingerprint_never_matches(a: list[int], b: list[int]) -> None:
    result = match_fingerprints(a, b)
    assert result.matched is False
    assert result.offset_ms is None
    assert result.overlap_ms == 0


def test_items_round_trip_through_storage_including_the_high_bit() -> None:
    items = [0, 1, 2**31, 2**32 - 1, 123456789]
    assert decode_items(encode_items(items)) == tuple(items)
    assert len(encode_items(items)) == 4 * len(items)


def test_decoding_bytes_that_are_not_whole_items_raises() -> None:
    with pytest.raises(ValueError, match="multiple of 4"):
        decode_items(b"\x00\x01\x02")


def test_index_keys_are_sampled_by_value_not_position() -> None:
    # Both sides of a comparison must pick the same items wherever they sit, or an
    # intro would shift every key away from its partner.
    assert index_keys(FATWA) == index_keys(noise(seconds(7), seed=13) + FATWA) - index_keys(
        noise(seconds(7), seed=13)
    )


def test_index_keys_keep_roughly_one_item_in_eight() -> None:
    keys = index_keys(FATWA)
    assert len(FATWA) / 12 < len(keys) < len(FATWA) / 5


def test_a_reencoded_copy_shares_enough_index_keys_to_be_found() -> None:
    shared = index_keys(FATWA) & index_keys(reencode(FATWA, seed=14))
    assert len(shared) >= 20
