"""Dedup layer 2: a byte-identical duplicate.

See docs/PIPELINE.md section 2, layer 2, and the ``entry.sha256`` UNIQUE column in
db/migrations/0001_init.sql. The cheapest and most certain of the five layers: computed
before any extraction, fetch or ASR touches the file, so it is cheap enough to run
synchronously on every bulk upload and reject on the spot. Unlike layers 3 and 4, a hit
here is never a candidate for a human to judge -- the same bytes once already mean the
same submission, so there is nothing left to decide.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path

#: Phone videos run to gigabytes; this keeps a hash's memory use flat regardless of
#: file size, which is what makes it cheap enough to run synchronously on every upload.
_DEFAULT_CHUNK_SIZE = 1024 * 1024


def sha256_of_file(path: Path, chunk_size: int = _DEFAULT_CHUNK_SIZE) -> str:
    """The hex digest of a file on disk, read in fixed-size chunks.

    Never ``path.read_bytes()`` here: an uploaded video can be larger than is sane to
    hold in memory at once, and the digest is identical either way.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_hex(data: bytes) -> str:
    """The hex digest stored as ``entry.sha256``.

    Lowercase hex, matching what every other tool in the pipeline (``sha256sum``,
    Postgres' own ``encode(digest(...), 'hex')``) produces, so a value computed here
    and one computed in SQL can be compared without a case-folding step either side
    might forget.
    """
    return hashlib.sha256(data).hexdigest()


def find_exact_duplicate(digest: str, known: Mapping[str, str]) -> str | None:
    """Look ``digest`` up against the corpus' known hashes.

    ``known`` maps ``sha256`` to ``entry.id``. Plain dict lookup, deliberately: at the
    corpus' realistic size this needs no index beyond the one the schema already has
    (``entry.sha256`` is ``UNIQUE``), and a caller backed by Postgres passes a mapping
    built from one indexed lookup, not the whole table.
    """
    return known.get(digest)


__all__ = ["find_exact_duplicate", "sha256_hex", "sha256_of_file"]
