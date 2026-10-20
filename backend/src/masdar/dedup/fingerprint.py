"""Dedup layer 3: the same recording with a different cut, intro or bitrate.

See docs/PIPELINE.md section 2, layer 3, and the ``entry_fingerprint`` table in
db/migrations/0001_init.sql.

Chromaprint is built for music. One print per file fails at exactly the normal case here:
the same fatwa with a different intro glued to the front. Overlapping windows fix it — if
three consecutive windows line up, it is the same recording, whatever sits in front of it.

Two limits, both deliberate:

* Windows only line up when the extra intro is a whole number of hops long. A 7 s intro
  shifts every window onto different audio and nothing compares equal. That gap is what
  layer 4 (SimHash over the transcript) is for; narrowing the hop would cost extraction
  time on every recording to buy very little.
* There is no extractor implementation here. A real one has to cut the window with
  ``ffmpeg -ss <offset> -t <extent>`` and feed it to ``fpcalc -raw``; that is a
  subprocess seam no unit test can honestly cover, so it stays behind the Protocol and
  is written and verified where ffmpeg actually exists.

Nothing in this module decides anything. The functions return findings; whether two
entries are the same recording, and which of them is canonical, is an admin's call.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

DEFAULT_WINDOW_MS = 30_000
DEFAULT_HOP_MS = 15_000


@dataclass(frozen=True)
class Window:
    """One fingerprint window. ``idx`` is ``entry_fingerprint.window_idx``."""

    idx: int
    offset_ms: int


def plan_windows(
    duration_ms: int,
    window_ms: int = DEFAULT_WINDOW_MS,
    hop_ms: int = DEFAULT_HOP_MS,
) -> list[Window]:
    """Plan the overlapping windows to fingerprint for a recording of ``duration_ms``.

    The last window may run past the end of the recording; the extractor clamps it. A
    further window is only planned while the previous one does not already reach the end,
    so a recording never gets a trailing sliver of audio as its own window.
    """
    if window_ms <= 0:
        raise ValueError("window_ms must be positive")
    if hop_ms <= 0:
        raise ValueError("hop_ms must be positive")
    if hop_ms > window_ms:
        # Gaps between windows would silently leave audio unfingerprinted, which is the
        # one failure this layer cannot afford: a missed window is a missed duplicate.
        raise ValueError("hop_ms must not exceed window_ms, windows have to overlap")
    if duration_ms < 0:
        raise ValueError("duration_ms must not be negative")

    if duration_ms == 0:
        return []

    windows = [Window(idx=0, offset_ms=0)]
    # Plan another window only while the previous one still ends before the recording
    # does. Because hop_ms <= window_ms this also keeps every offset inside the audio.
    while (len(windows) - 1) * hop_ms + window_ms < duration_ms:
        idx = len(windows)
        windows.append(Window(idx=idx, offset_ms=idx * hop_ms))
    return windows


class FingerprintExtractionError(RuntimeError):
    """A window produced no fingerprint at all."""


class FingerprintExtractor(Protocol):
    """How audio becomes a fingerprint. The only external dependency in this module.

    Implementations shell out to Chromaprint; tests use a fake. ``duration_ms`` is
    already clamped to what is left of the recording.
    """

    def extract(self, path: Path, offset_ms: int, duration_ms: int) -> bytes: ...


@dataclass(frozen=True)
class WindowFingerprint:
    """One row of ``entry_fingerprint``, minus the entry id."""

    window_idx: int
    offset_ms: int
    fingerprint: bytes


def fingerprint_recording(
    path: Path,
    duration_ms: int,
    extractor: FingerprintExtractor,
    window_ms: int = DEFAULT_WINDOW_MS,
    hop_ms: int = DEFAULT_HOP_MS,
) -> list[WindowFingerprint]:
    """Fingerprint every planned window of one recording.

    The result is dense: one row per planned window, in order. That is what makes a run
    of matching positions convertible to milliseconds via ``hop_ms``.
    """
    rows: list[WindowFingerprint] = []
    for window in plan_windows(duration_ms, window_ms=window_ms, hop_ms=hop_ms):
        extent = min(window_ms, duration_ms - window.offset_ms)
        fingerprint = extractor.extract(path, window.offset_ms, extent)
        if not fingerprint:
            # Storing an empty fingerprint would make this window compare equal to every
            # other failed window, inventing duplicates between unrelated recordings.
            raise FingerprintExtractionError(
                f"no fingerprint for {path} at offset_ms={window.offset_ms}"
            )
        rows.append(
            WindowFingerprint(
                window_idx=window.idx,
                offset_ms=window.offset_ms,
                fingerprint=fingerprint,
            )
        )
    return rows


@dataclass(frozen=True)
class FingerprintMatch:
    """What was found when two window sequences were compared.

    ``offset_shift`` is measured in windows, not milliseconds: it is ``j - i`` for a run
    where ``a[i]`` lines up with ``b[j]``. A positive value means b starts later, i.e. b
    has that many extra windows in front of it — typically an intro. Multiply by the
    hop used to plan the windows to get milliseconds. It is None only when not a single
    window matched.

    A match is a finding, not a verdict: the admin decides which entry is canonical.
    """

    matched: bool
    offset_shift: int | None
    run_length: int


def match_fingerprints(
    a: Sequence[bytes],
    b: Sequence[bytes],
    min_consecutive: int = 3,
) -> FingerprintMatch:
    """Find the longest run of consecutive windows that a and b share at some shift.

    This compares one pair of recordings and costs O(len(a) * (len(a) + len(b))). It is
    meant to run on candidates only: look individual window fingerprints up against the
    ``entry_fingerprint_lookup`` index first, then compare the handful of entries that
    come back. Running it across the whole corpus does not scale.
    """
    if min_consecutive < 1:
        raise ValueError("min_consecutive must be at least 1")

    best_run = 0
    best_shift: int | None = None

    for shift in range(-(len(a) - 1), len(b)) if a and b else ():
        run = 0
        for i in range(len(a)):
            j = i + shift
            if 0 <= j < len(b) and a[i] == b[j]:
                run += 1
                if run > best_run or (run == best_run and _closer(shift, best_shift)):
                    best_run, best_shift = run, shift
            else:
                run = 0

    return FingerprintMatch(
        matched=best_run >= min_consecutive,
        offset_shift=best_shift if best_run else None,
        run_length=best_run,
    )


def _closer(shift: int, incumbent: int | None) -> bool:
    """Tie-break between equally long runs, so the result is deterministic."""
    if incumbent is None:
        return True
    return (abs(shift), shift) < (abs(incumbent), incumbent)


__all__ = [
    "DEFAULT_HOP_MS",
    "DEFAULT_WINDOW_MS",
    "FingerprintExtractionError",
    "FingerprintExtractor",
    "FingerprintMatch",
    "Window",
    "WindowFingerprint",
    "fingerprint_recording",
    "match_fingerprints",
    "plan_windows",
]
