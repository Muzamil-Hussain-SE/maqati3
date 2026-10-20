/**
 * Locating the active transcript line during playback.
 *
 * A 20-minute fatwa is 150–250 lines; a long lecture is 800+. `timeupdate` fires
 * roughly four times a second, so a linear scan is thousands of comparisons per second
 * on the device the audience actually uses — a mid-range Android. Binary search makes
 * it ~10 comparisons regardless of length.
 */

export type Cue = {
  /** Row index in the transcript, 0-based. Stable across languages. */
  idx: number;
  startMs: number;
  endMs: number | null;
};

/**
 * Index of the cue covering `timeMs`, or -1 before the first cue starts.
 *
 * Cues are assumed sorted by `startMs` and non-overlapping — the ingest validator
 * enforces strictly increasing timestamps, so that holds for anything the API serves.
 *
 * A cue with `endMs === null` runs until the next cue begins; the last one runs to the
 * end of the recording. This matters because a contributor may leave a row's text empty
 * when merging two lines in a translation — the row still holds its own timestamp.
 */
export function findActiveCue(cues: readonly Cue[], timeMs: number): number {
  if (cues.length === 0 || timeMs < cues[0].startMs) return -1;

  let lo = 0;
  let hi = cues.length - 1;
  let best = -1;

  while (lo <= hi) {
    const mid = (lo + hi) >>> 1;
    if (cues[mid].startMs <= timeMs) {
      best = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }

  if (best === -1) return -1;

  // An explicit end that has already passed, with a gap before the next cue, means
  // nothing is active — silence between two utterances.
  const cue = cues[best];
  if (cue.endMs !== null && timeMs >= cue.endMs) {
    const next = cues[best + 1];
    if (!next || timeMs < next.startMs) return -1;
  }
  return best;
}

/** `HH:MM:SS.mmm`, the WebVTT timestamp form. */
export function formatVttTime(ms: number): string {
  const total = Math.max(0, Math.floor(ms));
  const h = Math.floor(total / 3_600_000);
  const m = Math.floor((total % 3_600_000) / 60_000);
  const s = Math.floor((total % 60_000) / 1000);
  const frac = total % 1000;
  const pad = (n: number, width = 2) => String(n).padStart(width, '0');
  return `${pad(h)}:${pad(m)}:${pad(s)}.${pad(frac, 3)}`;
}

/** `M:SS` or `H:MM:SS` — what a listener reads next to a line. */
export function formatClock(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, '0');
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}
