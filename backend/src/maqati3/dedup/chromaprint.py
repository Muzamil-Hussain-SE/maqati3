"""The real `FingerprintExtractor`: fpcalc, run once over the whole recording.

fpcalc decodes through FFmpeg itself, so a phone's MP4, an M4A, an Opus voice note and
an MP3 all go straight in, and it reports the duration too -- no separate ffmpeg or
ffprobe step. Covered by tests/test_dedup_chromaprint.py against the real binary.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from maqati3.dedup.fingerprint import ALGORITHM, Fingerprint, UnreadableMedia

#: Long enough for a two-hour lecture; a hung decoder must not hold a request forever.
DEFAULT_TIMEOUT_S = 600


class ChromaprintExtractor:
    """Runs ``fpcalc -json -raw -algorithm 2 -length 0`` and parses its output.

    ``-length 0`` fingerprints the whole file instead of fpcalc's default first two
    minutes: a duplicate whose shared part starts at minute five must still be found.
    The algorithm is pinned rather than left to fpcalc's default, so an upgrade that
    changes the default cannot silently make new fingerprints incomparable to stored
    ones.
    """

    def __init__(self, fpcalc: str = "fpcalc", timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        self._fpcalc = fpcalc
        self._timeout_s = timeout_s

    def extract(self, path: Path) -> Fingerprint:
        # A missing binary raises FileNotFoundError and is left to propagate: a broken
        # server must not tell a contributor that their video is unreadable.
        try:
            proc = subprocess.run(
                [
                    self._fpcalc,
                    "-json",
                    "-raw",
                    "-algorithm",
                    str(ALGORITHM),
                    "-length",
                    "0",
                    str(path),
                ],
                capture_output=True,
                timeout=self._timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            message = f"decoding {path.name} took longer than {self._timeout_s}s"
            raise UnreadableMedia(message) from exc
        if proc.returncode != 0:
            # fpcalc exits 2 with "ERROR: Could not find any audio stream" or "Could not
            # open the input file" on stderr -- a photo, a silent screen recording, a
            # document renamed to .mp4.
            message = proc.stderr.decode(errors="replace").strip() or f"exit {proc.returncode}"
            raise UnreadableMedia(message)

        data = json.loads(proc.stdout)
        return Fingerprint(
            items=tuple(int(item) & 0xFFFFFFFF for item in data.get("fingerprint", [])),
            duration_ms=round(float(data["duration"]) * 1000),
        )


__all__ = ["DEFAULT_TIMEOUT_S", "ChromaprintExtractor"]
