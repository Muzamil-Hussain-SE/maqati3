"""Dedup layer 4: the same content in a different recording.

See docs/PIPELINE.md section 2, layer 4. Audio fingerprinting never catches this case —
the same fatwa given on a different occasion, different microphone, same wording. At an
ASR word error rate of 20-40 % an exact text comparison is useless, so this works over
character shingles, which degrade gracefully under substituted words.

The caller passes already normalised text (``segment_text.text_norm``: tashkeel removed,
alef/hamza unified, punctuation stripped). This module deliberately does not import
``masdar.text`` and does no normalisation of its own: a hash computed over differently
normalised text is silently incomparable, so normalisation must happen once, upstream,
and be visible in the database.
"""

from __future__ import annotations

import hashlib

_BITS = 64
_MASK = (1 << _BITS) - 1


def _feature_hash(shingle: str) -> int:
    """A stable 64-bit hash.

    Not the builtin ``hash()``: it is salted per interpreter run, so stored hashes would
    stop matching after a restart.
    """
    digest = hashlib.blake2b(shingle.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def simhash(text: str, shingle_size: int = 4) -> int:
    """A 64-bit SimHash over character shingles of already normalised ``text``."""
    if shingle_size < 1:
        raise ValueError("shingle_size must be at least 1")
    if not text:
        return 0

    shingles = (
        [text[i : i + shingle_size] for i in range(len(text) - shingle_size + 1)]
        if len(text) >= shingle_size
        else [text]
    )

    weights = [0] * _BITS
    for shingle in shingles:
        h = _feature_hash(shingle)
        for bit in range(_BITS):
            weights[bit] += 1 if (h >> bit) & 1 else -1

    value = 0
    for bit in range(_BITS):
        if weights[bit] > 0:
            value |= 1 << bit
    return value & _MASK


def hamming(a: int, b: int) -> int:
    """Number of differing bits between two 64-bit SimHashes."""
    return ((a ^ b) & _MASK).bit_count()


def is_near_duplicate(a: int, b: int, threshold: int = 6) -> bool:
    """Whether two SimHashes are close enough to be flagged as the same content.

    The default threshold of 6 is the value fixed in docs/PIPELINE.md, layer 4. A hit is
    a finding for a human to confirm, never grounds to delete anything.
    """
    return hamming(a, b) <= threshold


def to_signed_64(value: int) -> int:
    """Reinterpret an unsigned 64-bit hash as the signed value Postgres stores.

    ``entry.simhash_ar`` is a bigint, which is signed: every hash with the top bit set
    is out of range unless it is reinterpreted first. ``hamming`` is unaffected either
    way, because it masks the XOR back down to 64 bits.
    """
    value &= _MASK
    return value - (1 << _BITS) if value >> (_BITS - 1) else value


def from_signed_64(value: int) -> int:
    """Inverse of :func:`to_signed_64`: a bigint read back as an unsigned 64-bit hash."""
    return value & _MASK


__all__ = [
    "from_signed_64",
    "hamming",
    "is_near_duplicate",
    "simhash",
    "to_signed_64",
]
