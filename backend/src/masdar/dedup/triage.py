"""What a freshly uploaded file is: a rejected duplicate, a candidate, or new.

Ties dedup layers 2 (exact.py) and 3 (fingerprint.py) together behind the boundary a
bulk upload has to cross *while the contributor is still on the page* (see
docs/ARCHITECTURE.md, "Revidiert 2026-10-25"): layer 2 is checked first because it is
free and certain, so a byte-identical file never pays for fingerprinting at all. Layer
3 then narrows the whole corpus down to a handful of candidates through one indexed
window lookup (`entry_fingerprint_lookup`) before paying for the O(n*m) comparison in
`match_fingerprints` -- see that module's own docstring on why it must not run
unindexed across the corpus.

Nothing here decides whether a candidate really is the same recording. That stays a
decision for the contributor who is looking at both, right now, with the existing
entry's audio to listen to -- or, for a shared window too weak to pass `min_consecutive`,
it is not even surfaced as a candidate at all.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from masdar.dedup.exact import find_exact_duplicate
from masdar.dedup.fingerprint import (
    FingerprintExtractor,
    FingerprintMatch,
    WindowFingerprint,
    fingerprint_recording,
    match_fingerprints,
)


class FingerprintIndex(Protocol):
    """The read surface `entry_fingerprint_lookup` needs to expose. No database driver
    is imported here, same reasoning as `api/repository.py`: the Postgres
    implementation is a single indexed lookup plus a per-entry row fetch, and tests
    exercise this module against a fake."""

    def entries_sharing_a_window(self, fingerprints: Sequence[bytes]) -> set[str]:
        """Every entry that has at least one window equal to one of ``fingerprints``.

        One query against the ``entry_fingerprint_lookup`` index (``fingerprint = ANY
        (...)``), not a scan -- this is what keeps the candidate search independent of
        corpus size.
        """
        ...

    def windows_of(self, entry_id: str) -> Sequence[bytes]:
        """``entry_id``'s own window fingerprints, in ``window_idx`` order."""
        ...


@dataclass(frozen=True, slots=True)
class ExactDuplicate:
    """Layer 2 matched. Rejected outright -- there is nothing left to decide."""

    entry_id: str


@dataclass(frozen=True, slots=True)
class FingerprintCandidate:
    """One entry layer 3 found plausible, and how strong the match was."""

    entry_id: str
    match: FingerprintMatch


@dataclass(frozen=True, slots=True)
class FingerprintCandidates:
    """At least one layer-3 candidate. The contributor decides; nothing is stored yet.

    ``candidates`` is sorted strongest match first, ties broken by ``entry_id`` so the
    order is deterministic. ``sha256`` and ``fingerprints`` travel with the result so
    that, if the contributor overrides and uploads anyway, nothing has to be
    recomputed.
    """

    sha256: str
    fingerprints: list[WindowFingerprint]
    candidates: list[FingerprintCandidate]


@dataclass(frozen=True, slots=True)
class NewUpload:
    """Neither layer matched anything. Proceeds into the normal pipeline."""

    sha256: str
    fingerprints: list[WindowFingerprint]


UploadTriage = ExactDuplicate | FingerprintCandidates | NewUpload


def triage_upload(
    path: Path,
    duration_ms: int,
    *,
    sha256: str,
    known_sha256: Mapping[str, str],
    extractor: FingerprintExtractor,
    index: FingerprintIndex,
    min_consecutive: int = 3,
) -> UploadTriage:
    """Decide what a freshly uploaded file at ``path`` is.

    ``sha256`` is computed by the caller (``exact.sha256_of_file``, streamed from the
    file already saved to disk) rather than here, so this function never has to read a
    multi-gigabyte upload itself just to hash it.
    """
    existing = find_exact_duplicate(sha256, known=known_sha256)
    if existing is not None:
        return ExactDuplicate(entry_id=existing)

    fingerprints = fingerprint_recording(path, duration_ms, extractor)
    if not fingerprints:
        # Nothing to look up: a recording too short to fingerprint can share no window
        # with anything, by construction, so querying the index would only cost time.
        return NewUpload(sha256=sha256, fingerprints=fingerprints)

    windows = [row.fingerprint for row in fingerprints]
    candidates = [
        FingerprintCandidate(entry_id=entry_id, match=match)
        for entry_id in index.entries_sharing_a_window(windows)
        for match in [
            match_fingerprints(
                windows, list(index.windows_of(entry_id)), min_consecutive=min_consecutive
            )
        ]
        if match.matched
    ]
    if not candidates:
        return NewUpload(sha256=sha256, fingerprints=fingerprints)

    candidates.sort(key=lambda candidate: (-candidate.match.run_length, candidate.entry_id))
    return FingerprintCandidates(sha256=sha256, fingerprints=fingerprints, candidates=candidates)


__all__ = [
    "ExactDuplicate",
    "FingerprintCandidate",
    "FingerprintCandidates",
    "FingerprintIndex",
    "NewUpload",
    "UploadTriage",
    "triage_upload",
]
