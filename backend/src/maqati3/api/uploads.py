"""The bulk-upload route's boundary to disk and to the corpus' known hashes.

Mirrors `api/repository.py`: Protocols plus the plain row type the route needs, and no
filesystem or subprocess code. The route is tested against fakes; the real
implementations (local disk, fpcalc, Postgres) are written and verified where those
systems exist, same reasoning as `dedup.fingerprint.FingerprintExtractor`. The other
two boundaries the route crosses -- `FingerprintExtractor` and `FingerprintIndex` --
are the dedup modules' own Protocols and are not restated here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol

from maqati3.dedup.fingerprint import Fingerprint

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
    """A received file, on disk, and its hash, computed while it was written."""

    path: Path
    sha256: str


class UploadStore(Protocol):
    """Where a freshly received file waits while it is triaged and decided on."""

    def stage(self, filename: str, stream: BinaryIO) -> StagedUpload:
        """Write the upload to disk, hashing it on the way in.

        One pass over the bytes, not two: a phone video can run to gigabytes, and the
        contributor is waiting on this call. Raises `UploadTooLarge` past the limit.
        """
        ...

    def discard(self, path: Path) -> None:
        """Remove a staged file nobody is going to keep."""
        ...

    def locate(self, path: Path) -> Path | None:
        """The file at ``path`` if it is a staged upload that still exists, else None.

        The only gate between a path read back from the database and a file served to a
        browser: anything outside the staging area is never handed out.
        """
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


class UploadTooLarge(ValueError):
    """The upload is bigger than the store accepts."""


class Submissions(Protocol):
    """Triaged uploads waiting for the contributor's decision, then for an admin."""

    def record(
        self,
        *,
        sha256: str,
        original_name: str,
        staged_path: Path,
        fingerprint: Fingerprint,
        candidate_keys: Sequence[str],
    ) -> bool:
        """Store a triaged upload. False if identical bytes were recorded first."""
        ...

    def keep(self, sha256: str, contributor: str) -> bool:
        """Send a pending upload in, under its sender's name. False if it is not
        awaiting a decision. Which scholar it is, and how sure anyone is, is settled when
        an admin registers it -- see migration 0004."""
        ...

    def drop(self, sha256: str) -> Path | None:
        """Delete a pending upload; its staged file, or None if nothing was pending."""
        ...

    def staged_path(self, sha256: str) -> Path | None:
        """Where a recorded submission's file was staged, or None if there is none."""
        ...


__all__ = [
    "SUBMISSION_PREFIX",
    "KnownHashes",
    "StagedUpload",
    "Submissions",
    "UploadStore",
    "UploadTooLarge",
    "is_submission_key",
    "submission_key",
]
