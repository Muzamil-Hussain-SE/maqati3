"""The disk where an upload waits while it is triaged and decided on.

Implements `api.uploads.UploadStore` on a local directory -- on the one Hetzner VM the
stack runs on (CLAUDE.md, "Stack"), a Docker volume is the real storage, not a stand-in.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path
from typing import BinaryIO

from masdar.api.uploads import StagedUpload, UploadTooLarge

#: A phone video of a long lecture runs to about this; anything larger is far more
#: likely a mistake (a whole camera roll zipped, a raw screen capture) than a fatwa.
DEFAULT_MAX_BYTES = 2 * 1024**3

_CHUNK = 1024 * 1024

#: Only the extension survives from the client's filename, and only a plain one. The
#: name itself is whatever the client sent -- never a path component on this disk.
_EXTENSION = re.compile(r"^\.[a-z0-9]{1,5}$")


class LocalUploadStore:
    def __init__(self, root: Path, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
        self._root = root
        self._max_bytes = max_bytes

    def stage(self, filename: str, stream: BinaryIO) -> StagedUpload:
        """Write the upload under a fresh random name, hashing it on the way in."""
        self._root.mkdir(parents=True, exist_ok=True)
        suffix = Path(filename).suffix.lower()
        path = self._root / (uuid.uuid4().hex + (suffix if _EXTENSION.match(suffix) else ""))

        digest = hashlib.sha256()
        written = 0
        try:
            with path.open("xb") as out:
                for chunk in iter(lambda: stream.read(_CHUNK), b""):
                    written += len(chunk)
                    if written > self._max_bytes:
                        raise UploadTooLarge(f"upload exceeds {self._max_bytes} bytes")
                    digest.update(chunk)
                    out.write(chunk)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return StagedUpload(path=path, sha256=digest.hexdigest())

    def discard(self, path: Path) -> None:
        """Remove a staged file. Refuses anything outside the staging directory: this
        deletes files, and the path it is handed comes back out of the database."""
        resolved = path.resolve()
        if resolved.parent != self._root.resolve():
            raise ValueError(f"refusing to delete {path}: outside the staging directory")
        resolved.unlink(missing_ok=True)

    def locate(self, path: Path) -> Path | None:
        resolved = path.resolve()
        if resolved.parent != self._root.resolve() or not resolved.is_file():
            return None
        return resolved


__all__ = ["DEFAULT_MAX_BYTES", "LocalUploadStore"]
