"""The bulk-upload route's boundary to disk and to the corpus' known hashes.

Mirrors `api/repository.py`: Protocols plus the plain row type the route needs, and no
filesystem or subprocess code. The route is tested against fakes; the real
implementations (local disk + ffprobe, Postgres) are written and verified where those
systems exist, same reasoning as `dedup.fingerprint.FingerprintExtractor`. The other
two boundaries the route crosses -- `FingerprintExtractor` and `FingerprintIndex` --
are the dedup modules' own Protocols and are not restated here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol


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


__all__ = ["KnownHashes", "StagedUpload", "UploadStore"]
