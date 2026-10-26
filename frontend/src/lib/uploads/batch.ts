/**
 * The logic of the bulk upload page, without any of its UI: what the link's key is,
 * what each file sends when the batch goes out, and what still stands in the way.
 *
 * A contributor says who they are and nothing else: which scholar a file is, and how
 * sure anyone is, is settled when an admin registers it (migration 0004).
 *
 * The server enforces every rule that matters (backend/src/maqati3/api/routes.py); the
 * checks here only explain them before a request is made, in the contributor's words.
 */

/** What `/api/v1/uploads` says about one matched entry or pending upload. */
export type MatchOut = {
  public: boolean;
  pending: boolean;
  preview_id: string | null;
  source_url: string | null;
  entry_id: string | null;
  scholar: { id: string; name_ar: string; name_en: string } | null;
  title_ar: string | null;
  title_en: string | null;
  duration_sec: number | null;
  overlap_ms: number | null;
};

/** What `/api/v1/uploads` says one uploaded file is. */
export type CheckOut = {
  sha256: string;
  status: 'rejected' | 'candidates' | 'new';
  duplicate_of: MatchOut | null;
  candidates: MatchOut[];
};

export type Phase =
  | 'queued'
  | 'uploading'
  | 'checking'
  | 'checked'
  | 'failed'
  | 'sending'
  | 'sent'
  | 'dropped';

export type Row = {
  id: string;
  name: string;
  size: number;
  phase: Phase;
  /** Upload progress, 0 to 1. */
  progress: number;
  check: CheckOut | null;
  /** For a candidate: did the contributor say it is the same recording, or a different one? */
  choice: 'keep' | 'drop' | null;
  error: string | null;
};

export type DecisionBody = { keep: false } | { keep: true; contributor: string };

export type Blocker =
  | { kind: 'busy' | 'empty' | 'name' }
  | { kind: 'undecided'; rowIds: string[] };

/** One batch, as the form had it: enough for a phone's worth of forwards at once. */
export const MAX_FILES = 20;

/**
 * The upload key from the link's fragment (`…/upload#k=…`). The fragment never leaves
 * the browser on its own -- not in server logs, not in a referrer -- so the page reads
 * it here and sends it as a header.
 */
export function parseUploadKey(hash: string): string | null {
  const key = new URLSearchParams(hash.replace(/^#/, '')).get('k');
  return key ? key : null;
}

/** Split newly chosen files into the ones that fit the batch and how many did not. */
export function takeFiles<T>(alreadyInBatch: number, files: T[]): { take: T[]; overflow: number } {
  const room = Math.max(0, MAX_FILES - alreadyInBatch);
  return { take: files.slice(0, room), overflow: Math.max(0, files.length - room) };
}

/** Whether this file goes out as "keep" when the batch is sent. */
function willKeep(row: Row): boolean {
  if (row.phase !== 'checked' || row.check === null) return false;
  if (row.check.status === 'new') return true;
  return row.check.status === 'candidates' && row.choice === 'keep';
}

/** What this file sends, or null when it sends nothing. */
export function decisionFor(
  row: Row,
  contributor: string,
): { sha256: string; body: DecisionBody } | null {
  if (row.phase !== 'checked' || row.check === null) return null;
  const { sha256, status } = row.check;
  if (status === 'rejected') return null;
  if (status === 'candidates' && row.choice === 'drop') return { sha256, body: { keep: false } };
  if (!willKeep(row)) return null;
  return { sha256, body: { keep: true, contributor: contributor.trim() } };
}

/** Everything that still prevents the batch from being sent. Empty means ready. */
export function blockers(rows: Row[], contributor: string): Blocker[] {
  const found: Blocker[] = [];
  if (rows.some((r) => r.phase === 'queued' || r.phase === 'uploading' || r.phase === 'checking')) {
    found.push({ kind: 'busy' });
  }

  const undecided = rows.filter(
    (r) => r.phase === 'checked' && r.check?.status === 'candidates' && r.choice === null,
  );
  if (undecided.length) found.push({ kind: 'undecided', rowIds: undecided.map((r) => r.id) });

  if (rows.some(willKeep) && !contributor.trim()) found.push({ kind: 'name' });

  const anything = rows.some(
    (r) => willKeep(r) || (r.check?.status === 'candidates' && r.choice !== null),
  );
  if (!anything && !found.some((b) => b.kind === 'busy' || b.kind === 'undecided')) {
    found.push({ kind: 'empty' });
  }
  return found;
}

/** `m:ss`, or `h:mm:ss` from an hour on -- the way a player shows time. */
export function formatDuration(ms: number): string {
  const total = Math.round(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = String(total % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`;
}
