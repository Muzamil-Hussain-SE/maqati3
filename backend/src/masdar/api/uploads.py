"""The bulk-upload route's boundary to disk and to the corpus' known hashes.

Mirrors `api/repository.py`: Protocols plus the plain row type the route needs, and no
filesystem or subprocess code. The route is tested against fakes; the real
implementations (local disk + ffprobe, Postgres) are written and verified where those
systems exist, same reasoning as `dedup.fingerprint.FingerprintExtractor`. The other
two boundaries the route crosses -- `FingerprintExtractor` and `FingerprintIndex` --
are the dedup modules' own Protocols and are not restated here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol

from masdar.dedup.fingerprint import WindowFingerprint
from masdar.domain import Attribution

#: Entries and pending submissions share one match-key namespace. An entry is its own
#: id ('uthaymin-000421', which never contains a colon); a submission is this prefix
#: plus its sha256. The fingerprint index and the known-hashes lookup speak it, the
#: route reads it.
SUBMISSION_PREFIX = "submission:"


def submission_key(sha256: str) -> str:
    return SUBMISSION_PREFIX + sha256


def is_submission_key(key: str) -> bool:
    return key.startswith(SUBMISSION_PREFIX)


@dataclass(frozen=True, slots=True)
class StagedUpload:
    """A received file, on disk, with what triage needs to know about it."""

    path: Path
    sha256: str
    duration_ms: int


class UploadStore(Protocol):
    """Where a freshly received file waits while it is triaged and decided on."""

    def stage(self, filename: str, stream: BinaryIO) -> StagedUpload:
        """Write the upload to disk, hashing it on the way in and probing its duration.

        One pass over the bytes, not two: a phone video can run to gigabytes, and the
        contributor is waiting on this call.
        """
        ...

    def discard(self, path: Path) -> None:
        """Remove a staged file nobody is going to keep."""
        ...


class KnownHashes(Protocol):
    """The corpus' `entry.sha256` values, for dedup layer 2."""

    def known(self) -> Mapping[str, str]:
        """Every known `sha256 -> entry.id`, across all entries, public or not.

        One query loading the whole column: at the corpus' realistic size (~3,000
        recordings, see CLAUDE.md) that is cheaper than a round trip per file.
        Withheld entries count too -- a duplicate of a held-back recording is still a
        duplicate, it just must not be named to the person uploading it.
        """
        ...


class InvalidMetadata(ValueError):
    """A kept upload names a scholar or topic the archive does not know."""


@dataclass(frozen=True, slots=True)
class SubmissionMetadata:
    """What the contributor said about a kept upload. Claims, not facts: attribution on
    the entry is still the admin's call, however sure the contributor was."""

    contributor: str | None
    scholar_id: str | None
    scholar_other: str | None
    topic_id: str | None
    claimed_attribution: Attribution
    source_note: str | None
    note: str | None


class Submissions(Protocol):
    """Triaged uploads waiting for the contributor's decision, then for an admin."""

    def record(
        self,
        *,
        sha256: str,
        original_name: str,
        staged_path: Path,
        duration_ms: int,
        fingerprints: Sequence[WindowFingerprint],
        candidate_keys: Sequence[str],
    ) -> bool:
        """Store a triaged upload. False if identical bytes were recorded first."""
        ...

    def keep(self, sha256: str, metadata: SubmissionMetadata) -> bool:
        """Send a pending upload in. False if it is not awaiting a decision.

        Raises `InvalidMetadata` for a scholar or topic id the archive does not know.
        """
        ...

    def drop(self, sha256: str) -> Path | None:
        """Delete a pending upload; its staged file, or None if nothing was pending."""
        ...


__all__ = [
    "SUBMISSION_PREFIX",
    "InvalidMetadata",
    "KnownHashes",
    "StagedUpload",
    "SubmissionMetadata",
    "Submissions",
    "UploadStore",
    "is_submission_key",
    "submission_key",
]
