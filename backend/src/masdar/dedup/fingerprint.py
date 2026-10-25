"""Dedup layer 3: the same recording, re-encoded, re-cut, or with something glued on.

See docs/PIPELINE.md section 2, layer 3, and migration 0003.

A forwarded clip is always re-encoded, and a re-encoded Chromaprint fingerprint is never
byte-identical to the original. Measured on real speech through AAC 64k, MP3 32k and
Opus 24k: 1-9 % of the bits differ, against ~48 % for unrelated speech, and roughly
half of the 32-bit items survive exactly. The first version of this layer compared
fingerprints for equality and so could only ever have caught what layer 2 (SHA-256)
already catches. This one:

1. fingerprints the whole recording once (`fpcalc -raw -length 0`),
2. aligns two recordings by voting on the items that survive re-encoding -- to one
   item, ~0.12 s, so an intro of any length lines up,
3. confirms the alignment by the bit error rate, judged on the longest stretch that
   agrees rather than averaged over everything that overlaps: a forwarded compilation
   holding this fatwa *and* another must still match, and two episodes that share only
   a programme jingle must not.

The thresholds were measured on synthetic Arabic speech, which is cleaner than old
cassette material. Re-check them against real recordings before trusting them at scale.

Nothing here decides anything. A match is shown to the contributor, who decides.
"""

from __future__ import annotations

import struct
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

#: The Chromaprint algorithm every stored fingerprint was made with. Fingerprints of
#: different algorithms are not comparable, so it is pinned and stored, never assumed.
ALGORITHM = 2

#: Milliseconds between two fingerprint items: Chromaprint's 4096-sample frames advance
#: by a third of a frame at 11025 Hz.
ITEM_MS = 4096 / 3 / 11025 * 1000

#: Above this, a stretch is not the same audio. Re-encodes measured 0.008-0.085,
#: unrelated speech ~0.48; the margin is deliberate, because a false candidate costs
#: the contributor one listen and a missed one costs a duplicate in the archive.
MAX_BIT_ERROR_RATE = 0.20

#: The agreeing stretch must last this long...
MIN_OVERLAP_MS = 10_000

#: ...and cover this share of the shorter recording. A shared 15 s programme jingle in
#: front of two different three-minute fatawa covers 8 %, and is not a match.
MIN_OVERLAP_SHARE = 0.5

#: Agreement is judged over windows of this many items (~5 s), so a few bad items --
#: a click, a dropout -- do not split one long agreeing stretch into short ones.
AGREEMENT_WINDOW = 40

#: One stored item in this many becomes an index key, chosen by value so that both
#: recordings pick the same items wherever they sit. About one key per second of audio.
KEY_SAMPLING = 8

#: An owner sharing fewer index keys than this is not compared at all.
MIN_SHARED_KEYS = 3

#: An item value occurring more often than this in one recording -- silence, hum --
#: says nothing about alignment and would make voting quadratic, so it gets no vote.
MAX_POSITIONS_PER_ITEM = 16

#: How many of the best-voted alignments are checked in full.
ALIGNMENTS_TRIED = 5


@dataclass(frozen=True, slots=True)
class Fingerprint:
    """A whole recording's Chromaprint items, unsigned 32-bit, and its duration."""

    items: tuple[int, ...]
    duration_ms: int


class UnreadableMedia(ValueError):
    """The file has no audio stream that could be decoded."""


class FingerprintExtractor(Protocol):
    """How a file becomes a fingerprint. The only external dependency of this layer.

    Implemented by `dedup.chromaprint` over fpcalc; tests use a fake. Raises
    `UnreadableMedia` for anything without decodable audio.
    """

    def extract(self, path: Path) -> Fingerprint: ...


def encode_items(items: Sequence[int]) -> bytes:
    """Items as stored: big-endian unsigned 32-bit, four bytes each."""
    return struct.pack(f">{len(items)}I", *items)


def decode_items(data: bytes) -> tuple[int, ...]:
    if len(data) % 4:
        raise ValueError(f"stored fingerprint is {len(data)} bytes, not a multiple of 4")
    return struct.unpack(f">{len(data) // 4}I", data)


def index_keys(items: Sequence[int]) -> frozenset[int]:
    """The items of a recording that go into the lookup index.

    Sampled by value through a multiplicative hash, not by position: an intro shifts
    every position, but leaves the surviving values -- and so the chosen keys -- alone.
    """
    threshold = (1 << 32) // KEY_SAMPLING
    return frozenset(item for item in items if (item * 2654435761) & 0xFFFFFFFF < threshold)


@dataclass(frozen=True, slots=True)
class FingerprintMatch:
    """How two recordings line up.

    ``offset_ms`` is how much later b's copy of the shared audio starts than a's: a
    positive value means b has that much extra in front of it, typically an intro. It is
    None when no alignment was found at all. ``overlap_ms`` and ``bit_error_rate``
    describe the longest stretch that agrees at that alignment.

    A match is a finding, not a verdict: the contributor decides.
    """

    matched: bool
    offset_ms: int | None
    overlap_ms: int
    bit_error_rate: float | None


_NO_MATCH = FingerprintMatch(matched=False, offset_ms=None, overlap_ms=0, bit_error_rate=None)


def match_fingerprints(
    a: Sequence[int],
    b: Sequence[int],
    *,
    max_bit_error_rate: float = MAX_BIT_ERROR_RATE,
    min_overlap_ms: int = MIN_OVERLAP_MS,
    min_overlap_share: float = MIN_OVERLAP_SHARE,
) -> FingerprintMatch:
    """Find the best alignment of two recordings and judge whether they are the same."""
    if not a or not b:
        return _NO_MATCH

    positions: dict[int, list[int]] = {}
    for j, item in enumerate(b):
        positions.setdefault(item, []).append(j)
    votes: Counter[int] = Counter()
    for i, item in enumerate(a):
        found = positions.get(item, ())
        if len(found) <= MAX_POSITIONS_PER_ITEM:
            votes.update(j - i for j in found)
    if not votes:
        return _NO_MATCH

    # Longest agreement first; among equals the cleaner one, then the smaller shift in
    # absolute terms, so the result never depends on Counter's order for ties.
    run, ber, shift = max(
        (
            (*_longest_agreeing_run(a, b, shift, max_bit_error_rate), shift)
            for shift, _ in votes.most_common(ALIGNMENTS_TRIED)
        ),
        key=lambda tried: (tried[0], -tried[1], -abs(tried[2])),
    )

    overlap_ms = round(run * ITEM_MS)
    shorter_ms = min(len(a), len(b)) * ITEM_MS
    matched = (
        run > 0 and overlap_ms >= min_overlap_ms and overlap_ms >= min_overlap_share * shorter_ms
    )
    return FingerprintMatch(
        matched=matched,
        offset_ms=round(shift * ITEM_MS),
        overlap_ms=overlap_ms,
        bit_error_rate=ber if run else None,
    )


def _longest_agreeing_run(
    a: Sequence[int], b: Sequence[int], shift: int, max_bit_error_rate: float
) -> tuple[int, float]:
    """Length in items of the longest stretch where a and b agree at ``shift``, and the
    bit error rate over that stretch. (0, 1.0) if nothing agrees."""
    start_a = max(0, -shift)
    end_a = min(len(a), len(b) - shift)
    errors = [(a[i] ^ b[i + shift]).bit_count() for i in range(start_a, end_a)]
    n = len(errors)
    if n == 0:
        return 0, 1.0

    prefix = [0]
    for error in errors:
        prefix.append(prefix[-1] + error)

    window = min(AGREEMENT_WINDOW, n)
    budget = max_bit_error_rate * 32 * window
    # Every window that agrees marks all of its items as covered; the longest covered
    # stretch is the answer. A difference array keeps it linear.
    covered = [0] * (n + 1)
    for end in range(window, n + 1):
        if prefix[end] - prefix[end - window] <= budget:
            covered[end - window] += 1
            covered[end] -= 1

    best_start, best_len, run_start, depth = 0, 0, 0, 0
    for k in range(n):
        depth += covered[k]
        if depth > 0:
            if k - run_start + 1 > best_len:
                best_start, best_len = run_start, k - run_start + 1
        else:
            run_start = k + 1
    if best_len == 0:
        return 0, 1.0
    bits = prefix[best_start + best_len] - prefix[best_start]
    return best_len, bits / (32 * best_len)


__all__ = [
    "AGREEMENT_WINDOW",
    "ALGORITHM",
    "ITEM_MS",
    "KEY_SAMPLING",
    "MAX_BIT_ERROR_RATE",
    "MIN_OVERLAP_MS",
    "MIN_OVERLAP_SHARE",
    "MIN_SHARED_KEYS",
    "Fingerprint",
    "FingerprintExtractor",
    "FingerprintMatch",
    "UnreadableMedia",
    "decode_items",
    "encode_items",
    "index_keys",
    "match_fingerprints",
]
