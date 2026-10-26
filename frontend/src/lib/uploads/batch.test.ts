import { describe, expect, it } from 'vitest';
import {
  MAX_FILES,
  blockers,
  decisionFor,
  formatDuration,
  parseUploadKey,
  takeFiles,
  type CheckOut,
  type Row,
} from './batch';

function check(status: CheckOut['status'], sha256 = 'abc'): CheckOut {
  return { sha256, status, duplicate_of: null, candidates: [] };
}

function row(overrides: Partial<Row> = {}): Row {
  return {
    id: 'r1',
    name: 'clip.mp4',
    size: 1000,
    phase: 'checked',
    progress: 1,
    check: check('new'),
    choice: null,
    error: null,
    ...overrides,
  };
}

describe('parseUploadKey', () => {
  it('reads the key from the link fragment', () => {
    expect(parseUploadKey('#k=abc123')).toBe('abc123');
  });

  it('decodes it and ignores anything else in the fragment', () => {
    expect(parseUploadKey('#x=1&k=a%2Bb&y=2')).toBe('a+b');
  });

  it('is null for a link without a key', () => {
    expect(parseUploadKey('')).toBeNull();
    expect(parseUploadKey('#')).toBeNull();
    expect(parseUploadKey('#k=')).toBeNull();
  });
});

describe('takeFiles', () => {
  it('takes files up to the batch limit and reports the rest', () => {
    const files = Array.from({ length: 5 }, (_, i) => i);
    expect(takeFiles(MAX_FILES - 2, files)).toEqual({ take: [0, 1], overflow: 3 });
  });

  it('takes everything when there is room', () => {
    expect(takeFiles(0, [1, 2])).toEqual({ take: [1, 2], overflow: 0 });
  });
});

describe('decisionFor', () => {
  it('sends a new file under its sender', () => {
    expect(decisionFor(row(), 'Abdullah')).toEqual({
      sha256: 'abc',
      body: { keep: true, contributor: 'Abdullah' },
    });
  });

  it('trims the name', () => {
    expect(decisionFor(row(), '  Abdullah ')?.body).toEqual({
      keep: true,
      contributor: 'Abdullah',
    });
  });

  it('drops a candidate the contributor recognised as the same recording', () => {
    const decision = decisionFor(row({ check: check('candidates'), choice: 'drop' }), 'Abdullah');
    expect(decision).toEqual({ sha256: 'abc', body: { keep: false } });
  });

  it('keeps a candidate the contributor said is a different recording', () => {
    const decision = decisionFor(row({ check: check('candidates'), choice: 'keep' }), 'Abdullah');
    expect(decision?.body).toEqual({ keep: true, contributor: 'Abdullah' });
  });

  it('sends nothing for a rejected duplicate -- the server already removed it', () => {
    expect(decisionFor(row({ check: check('rejected') }), 'A')).toBeNull();
  });

  it('sends nothing for a file that never got checked', () => {
    expect(decisionFor(row({ phase: 'failed', check: null }), 'A')).toBeNull();
  });
});

describe('blockers', () => {
  it('blocks while files are still uploading or being checked', () => {
    expect(blockers([row({ phase: 'uploading', check: null })], 'A')).toContainEqual({
      kind: 'busy',
    });
  });

  it('blocks until every candidate is decided', () => {
    const undecided = row({ id: 'r2', check: check('candidates') });
    expect(blockers([row(), undecided], 'A')).toContainEqual({
      kind: 'undecided',
      rowIds: ['r2'],
    });
  });

  it('blocks a batch with no name, because the admin must know who sent it', () => {
    expect(blockers([row()], '')).toContainEqual({ kind: 'name' });
    expect(blockers([row()], '   ')).toContainEqual({ kind: 'name' });
  });

  it('does not ask for a name when every file is being dropped', () => {
    const dropped = row({ check: check('candidates'), choice: 'drop' });
    expect(blockers([dropped], '')).toEqual([]);
  });

  it('blocks a batch with nothing to send', () => {
    expect(blockers([row({ check: check('rejected') })], 'A')).toContainEqual({ kind: 'empty' });
  });

  it('is clear for a ready batch', () => {
    expect(blockers([row()], 'Abdullah')).toEqual([]);
  });
});

describe('formatDuration', () => {
  it('writes minutes and seconds, and hours when there are any', () => {
    expect(formatDuration(90_000)).toBe('1:30');
    expect(formatDuration(5_000)).toBe('0:05');
    expect(formatDuration(3_725_400)).toBe('1:02:05');
  });
});
