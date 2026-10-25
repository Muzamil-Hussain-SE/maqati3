import { describe, expect, it } from 'vitest';
import {
  MAX_FILES,
  blockers,
  decisionFor,
  formatDuration,
  parseUploadKey,
  takeFiles,
  type CheckOut,
  type Details,
  type Row,
} from './batch';

const DEFAULTS: Details = {
  scholarId: 'ibn-uthaymin',
  scholarOther: '',
  confidence: 'probably',
  topicId: null,
  sourceNote: 'WhatsApp group',
};

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
    overrides: null,
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
  it('sends a new file with what the contributor said about it', () => {
    expect(decisionFor(row(), DEFAULTS, 'Abdullah')).toEqual({
      sha256: 'abc',
      body: {
        keep: true,
        contributor: 'Abdullah',
        scholar_id: 'ibn-uthaymin',
        scholar_other: null,
        topic_id: null,
        claimed_attribution: 'probably',
        source_note: 'WhatsApp group',
      },
    });
  });

  it('lets one file differ from the batch', () => {
    const decision = decisionFor(
      row({ overrides: { scholarId: null, scholarOther: 'Shaykh Rabi', confidence: 'not_sure' } }),
      DEFAULTS,
      'Abdullah',
    );
    expect(decision?.body).toMatchObject({
      scholar_id: null,
      scholar_other: 'Shaykh Rabi',
      claimed_attribution: 'not_sure',
    });
  });

  it('drops a candidate the contributor recognised as the same recording', () => {
    const decision = decisionFor(
      row({ check: check('candidates'), choice: 'drop' }),
      DEFAULTS,
      'Abdullah',
    );
    expect(decision).toEqual({ sha256: 'abc', body: { keep: false } });
  });

  it('keeps a candidate the contributor said is a different recording', () => {
    const decision = decisionFor(
      row({ check: check('candidates'), choice: 'keep' }),
      DEFAULTS,
      'Abdullah',
    );
    expect(decision?.body.keep).toBe(true);
  });

  it('sends nothing for a rejected duplicate -- the server already removed it', () => {
    expect(decisionFor(row({ check: check('rejected') }), DEFAULTS, 'A')).toBeNull();
  });

  it('sends nothing for a file that never got checked', () => {
    expect(decisionFor(row({ phase: 'failed', check: null }), DEFAULTS, 'A')).toBeNull();
  });
});

describe('blockers', () => {
  it('blocks while files are still uploading or being checked', () => {
    expect(blockers([row({ phase: 'uploading', check: null })], DEFAULTS)).toContainEqual({
      kind: 'busy',
    });
  });

  it('blocks until every candidate is decided', () => {
    const undecided = row({ id: 'r2', check: check('candidates') });
    expect(blockers([row(), undecided], DEFAULTS)).toContainEqual({
      kind: 'undecided',
      rowIds: ['r2'],
    });
  });

  it('blocks a kept file that does not say whose words these are', () => {
    const noScholar: Details = { ...DEFAULTS, scholarId: null, scholarOther: '  ' };
    expect(blockers([row()], noScholar)).toContainEqual({ kind: 'scholar', rowIds: ['r1'] });
  });

  it('blocks a kept file without the contributor’s confidence', () => {
    expect(blockers([row()], { ...DEFAULTS, confidence: null })).toContainEqual({
      kind: 'confidence',
      rowIds: ['r1'],
    });
  });

  it('does not ask for details on a file that is being dropped', () => {
    const dropped = row({ check: check('candidates'), choice: 'drop' });
    expect(blockers([dropped], { ...DEFAULTS, scholarId: null, confidence: null })).toEqual([]);
  });

  it('blocks a batch with nothing to send', () => {
    expect(blockers([row({ check: check('rejected') })], DEFAULTS)).toContainEqual({
      kind: 'empty',
    });
  });

  it('is clear for a ready batch', () => {
    expect(blockers([row()], DEFAULTS)).toEqual([]);
  });
});

describe('formatDuration', () => {
  it('writes minutes and seconds, and hours when there are any', () => {
    expect(formatDuration(90_000)).toBe('1:30');
    expect(formatDuration(5_000)).toBe('0:05');
    expect(formatDuration(3_725_400)).toBe('1:02:05');
  });
});
