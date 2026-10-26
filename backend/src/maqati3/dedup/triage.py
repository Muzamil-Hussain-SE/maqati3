"""What a freshly uploaded file is: a rejected duplicate, a candidate, or new.

Ties dedup layers 2 (exact.py) and 3 (fingerprint.py) together behind the boundary a
bulk upload has to cross *while the contributor is still on the page* (see
docs/ARCHITECTURE.md, "Revidiert 2026-10-25"). Layer 2 runs first because it is free
and certain: a byte-identical file is never decoded at all. Layer 3 then narrows the
whole corpus to a handful of owners through the key index before paying for a full
comparison against each.

Nothing here decides whether a candidate really is the same recording. That stays with
the contributor, who is looking at both right now.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from maqati3.dedup.exact import find_exact_duplicate
from maqati3.dedup.fingerprint import (
    Fingerprint,
    FingerprintExtractor,
    FingerprintMatch,
    index_keys,
    match_fingerprints,
)


class FingerprintIndex(Protocol):
    """The read surface the key index exposes. No database driver is imported here,
    same reasoning as `api/repository.py`; `db.submissions` implements it."""

    def candidates(self, keys: Set[int]) -> set[str]:
        """Every owner -- entry id or submission key -- sharing enough of ``keys`` to
        be worth a full comparison. One indexed lookup, not a scan."""
        ...

    def items_of(self, key: str) -> Sequence[int]:
        """The stored fingerprint items of one owner."""
        ...


@dataclass(frozen=True, slots=True)
class ExactDuplicate:
    """Layer 2 matched. Rejected outright -- there is nothing left to decide."""

    entry_id: str


@dataclass(frozen=True, slots=True)
class FingerprintCandidate:
    """One owner layer 3 found to line up, and how well."""

    entry_id: str
    match: FingerprintMatch


@dataclass(frozen=True, slots=True)
class FingerprintCandidates:
    """At least one layer-3 candidate. The contributor decides.

    ``candidates`` is ordered by how much of the recording agrees, longest first, ties
    broken by key so the order is deterministic. The fingerprint travels with the
    result so that keeping the file needs nothing recomputed.
    """

    sha256: str
    fingerprint: Fingerprint
    candidates: list[FingerprintCandidate]


@dataclass(frozen=True, slots=True)
class NewUpload:
    """Neither layer matched anything."""

    sha256: str
    fingerprint: Fingerprint


UploadTriage = ExactDuplicate | FingerprintCandidates | NewUpload


def triage_upload(
    path: Path,
    *,
    sha256: str,
    known_sha256: Mapping[str, str],
    extractor: FingerprintExtractor,
    index: FingerprintIndex,
) -> UploadTriage:
    """Decide what a freshly uploaded file at ``path`` is.

    ``sha256`` is computed by the caller while the upload streams to disk, so this
    never reads a multi-gigabyte file just to hash it. Raises
    `fingerprint.UnreadableMedia` for a file without decodable audio.
    """
    existing = find_exact_duplicate(sha256, known=known_sha256)
    if existing is not None:
        return ExactDuplicate(entry_id=existing)

    fingerprint = extractor.extract(path)
    if not fingerprint.items:
        return NewUpload(sha256=sha256, fingerprint=fingerprint)

    candidates = [
        FingerprintCandidate(entry_id=key, match=match)
        for key in index.candidates(index_keys(fingerprint.items))
        for match in [match_fingerprints(fingerprint.items, index.items_of(key))]
        if match.matched
    ]
    if not candidates:
        return NewUpload(sha256=sha256, fingerprint=fingerprint)

    candidates.sort(key=lambda candidate: (-candidate.match.overlap_ms, candidate.entry_id))
    return FingerprintCandidates(sha256=sha256, fingerprint=fingerprint, candidates=candidates)


__all__ = [
    "ExactDuplicate",
    "FingerprintCandidate",
    "FingerprintCandidates",
    "FingerprintIndex",
    "NewUpload",
    "UploadTriage",
    "triage_upload",
]
