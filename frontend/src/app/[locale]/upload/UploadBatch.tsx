'use client';

import { useLocale, useTranslations } from 'next-intl';
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import {
  UploadError,
  fetchScholars,
  fetchTopics,
  mediaUrl,
  sendDecision,
  uploadFile,
  type ScholarItem,
  type TopicItem,
} from '@/lib/uploads/api';
import {
  MAX_FILES,
  blockers,
  decisionFor,
  effectiveDetails,
  formatDuration,
  parseUploadKey,
  takeFiles,
  type Confidence,
  type Details,
  type MatchOut,
  type Row,
} from '@/lib/uploads/batch';

/** Two at a time: fingerprinting is CPU-bound on one small server, and a phone's upload
 * bandwidth does not get faster by being split twenty ways. */
const CONCURRENT_UPLOADS = 2;

const CONTRIBUTOR_KEY = 'masdar.contributor';

const EMPTY_DETAILS: Details = {
  scholarId: null,
  scholarOther: '',
  confidence: null,
  topicId: null,
  sourceNote: '',
};

function remember(name: string) {
  try {
    localStorage.setItem(CONTRIBUTOR_KEY, name);
  } catch {
    // private mode: the name just has to be typed again next time
  }
}

function recall(): string {
  try {
    return localStorage.getItem(CONTRIBUTOR_KEY) ?? '';
  } catch {
    return '';
  }
}

function subscribeToHash(onChange: () => void): () => void {
  window.addEventListener('hashchange', onChange);
  return () => window.removeEventListener('hashchange', onChange);
}

function errorCode(error: unknown): string {
  return error instanceof UploadError ? error.code : 'network';
}

function megabytes(bytes: number): string {
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function UploadBatch() {
  const t = useTranslations('upload');
  // The key lives in the link's #fragment, which only the browser knows. On the server
  // (and during hydration) there is no hash yet: `undefined` renders nothing until there is.
  const hash = useSyncExternalStore(subscribeToHash, () => window.location.hash, () => null);
  const key = hash === null ? undefined : parseUploadKey(hash);
  // Read once on the first client render; nothing that uses it is rendered before `key`.
  const [contributor, setContributor] = useState(() =>
    typeof window === 'undefined' ? '' : recall(),
  );
  const [scholars, setScholars] = useState<ScholarItem[]>([]);
  const [topics, setTopics] = useState<TopicItem[]>([]);
  const [defaults, setDefaults] = useState<Details>(EMPTY_DETAILS);
  const [rows, setRows] = useState<Row[]>([]);
  const [files, setFiles] = useState<Record<string, File>>({});
  const [overflow, setOverflow] = useState(0);
  const [sentCount, setSentCount] = useState<number | null>(null);
  // Which rows' uploads have been started. Effect-only bookkeeping, never rendered.
  const started = useRef(new Set<string>());

  useEffect(() => {
    fetchScholars().then(setScholars, () => setScholars([]));
    fetchTopics().then(setTopics, () => setTopics([]));
  }, []);

  const update = useCallback((id: string, patch: Partial<Row>) => {
    setRows((current) => current.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  }, []);

  // The upload queue: start queued files while fewer than CONCURRENT_UPLOADS are in flight.
  useEffect(() => {
    if (!key) return;
    const active = rows.filter((r) => r.phase === 'uploading' || r.phase === 'checking').length;
    const next = rows
      .filter((r) => r.phase === 'queued' && !started.current.has(r.id))
      .slice(0, Math.max(0, CONCURRENT_UPLOADS - active));
    for (const row of next) {
      const file = files[row.id];
      if (!file) continue;
      started.current.add(row.id);
      update(row.id, { phase: 'uploading', progress: 0, error: null });
      uploadFile(file, key, (fraction) =>
        update(row.id, fraction >= 1 ? { progress: 1, phase: 'checking' } : { progress: fraction }),
      )
        .then((check) => update(row.id, { phase: 'checked', check }))
        .catch((error) => update(row.id, { phase: 'failed', error: errorCode(error) }));
    }
  }, [rows, files, key, update]);

  // Files that were checked but not sent are waiting on the server. Leaving loses them.
  useEffect(() => {
    const unsent = rows.some((r) => r.phase === 'checked' && r.check?.status !== 'rejected');
    if (!unsent) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [rows]);

  const addFiles = (chosen: File[]) => {
    const media = chosen.filter((f) => f.type.startsWith('video/') || f.type.startsWith('audio/') || !f.type);
    const { take, overflow: left } = takeFiles(rows.length, media);
    setOverflow(left);
    setSentCount(null);
    const ids = take.map(() => crypto.randomUUID());
    setFiles((current) => ({ ...current, ...Object.fromEntries(ids.map((id, i) => [id, take[i]])) }));
    const added = take.map((file, i) => {
      const id = ids[i];
      return {
        id,
        name: file.name,
        size: file.size,
        phase: 'queued',
        progress: 0,
        check: null,
        choice: null,
        overrides: null,
        error: null,
      } satisfies Row;
    });
    setRows((current) => [...current, ...added]);
  };

  const removeRow = (row: Row) => {
    // A checked file is waiting on the server; tell it this one is not coming.
    if (key && row.phase === 'checked' && row.check && row.check.status !== 'rejected') {
      sendDecision(row.check.sha256, { keep: false }, key).catch(() => undefined);
    }
    setFiles((current) => {
      const rest = { ...current };
      delete rest[row.id];
      return rest;
    });
    setRows((current) => current.filter((r) => r.id !== row.id));
  };

  const retry = (row: Row) => {
    started.current.delete(row.id);
    update(row.id, { phase: 'queued', error: null, progress: 0 });
  };

  const send = async () => {
    if (!key) return;
    remember(contributor);
    let sent = 0;
    for (const row of rows) {
      const decision = decisionFor(row, defaults, contributor);
      if (!decision) continue;
      update(row.id, { phase: 'sending', error: null });
      try {
        await sendDecision(decision.sha256, decision.body, key);
        update(row.id, { phase: decision.body.keep ? 'sent' : 'dropped' });
        if (decision.body.keep) sent += 1;
      } catch (error) {
        update(row.id, { phase: 'checked', error: errorCode(error) });
      }
    }
    setSentCount(sent);
  };

  const startOver = () => {
    setFiles({});
    started.current.clear();
    setRows([]);
    setSentCount(null);
    setOverflow(0);
  };

  const blocked = blockers(rows, defaults);
  const sendable = rows.filter((r) => decisionFor(r, defaults, contributor) !== null).length;
  const finished =
    sentCount !== null && rows.every((r) => !['checked', 'sending', 'queued', 'uploading', 'checking'].includes(r.phase) || r.check?.status === 'rejected');

  if (key === undefined) return null;
  if (key === null) {
    return <p className="rounded-lg bg-amber-50 p-4 text-amber-900 dark:bg-amber-950 dark:text-amber-100">{t('badLink')}</p>;
  }

  return (
    <div className="space-y-8">
      <label className="block">
        <span className="mb-1 block text-sm font-semibold">{t('yourName')}</span>
        <input
          className="w-full rounded-md border border-neutral-300 bg-transparent px-3 py-2 dark:border-neutral-700"
          value={contributor}
          onChange={(e) => setContributor(e.target.value)}
          onBlur={() => remember(contributor)}
          autoComplete="name"
        />
      </label>

      <section className="space-y-4 rounded-xl border border-neutral-200 p-4 dark:border-neutral-800">
        <div>
          <h2 className="text-lg font-semibold">{t('aboutFiles')}</h2>
          <p className="text-sm text-neutral-600 dark:text-neutral-400">{t('aboutFilesHint')}</p>
        </div>
        <DetailsEditor
          value={defaults}
          onChange={(patch) => setDefaults((d) => ({ ...d, ...patch }))}
          scholars={scholars}
          topics={topics}
          withSource
        />
      </section>

      <DropZone onFiles={addFiles} />
      {overflow > 0 && (
        <p className="text-sm text-amber-800 dark:text-amber-200">{t('tooMany', { max: MAX_FILES, count: overflow })}</p>
      )}

      {rows.length > 0 && (
        <ul className="space-y-3">
          {rows.map((row) => (
            <FileRow
              key={row.id}
              row={row}
              file={files[row.id]}
              uploadKey={key}
              defaults={defaults}
              scholars={scholars}
              topics={topics}
              onChoose={(choice) => update(row.id, { choice })}
              onOverride={(patch) => update(row.id, { overrides: { ...row.overrides, ...patch } })}
              onRemove={() => removeRow(row)}
              onRetry={() => retry(row)}
            />
          ))}
        </ul>
      )}

      {finished ? (
        <div className="space-y-3 rounded-xl bg-emerald-50 p-4 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100">
          <p>{t('done', { sent: sentCount ?? 0 })}</p>
          <button type="button" onClick={startOver} className="rounded-md bg-emerald-700 px-4 py-2 font-semibold text-white">
            {t('more')}
          </button>
        </div>
      ) : (
        rows.length > 0 && (
          <div className="space-y-2">
            {blocked.map((b) => (
              <p key={b.kind} className="text-sm text-neutral-700 dark:text-neutral-300">
                {t(`blocked.${b.kind}`)}
              </p>
            ))}
            <button
              type="button"
              disabled={blocked.length > 0}
              onClick={send}
              className="w-full rounded-lg bg-emerald-700 px-4 py-3 text-lg font-semibold text-white disabled:cursor-not-allowed disabled:bg-neutral-400"
            >
              {t('send', { count: sendable })}
            </button>
          </div>
        )
      )}
    </div>
  );
}

function DropZone({ onFiles }: { onFiles: (files: File[]) => void }) {
  const t = useTranslations('upload');
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        onFiles(Array.from(e.dataTransfer.files));
      }}
      className={`rounded-xl border-2 border-dashed p-6 text-center ${over ? 'border-emerald-600 bg-emerald-50 dark:bg-emerald-950' : 'border-neutral-300 dark:border-neutral-700'}`}
    >
      <input
        ref={input}
        type="file"
        multiple
        accept="video/*,audio/*"
        className="hidden"
        onChange={(e) => {
          onFiles(Array.from(e.target.files ?? []));
          e.target.value = '';
        }}
      />
      <button
        type="button"
        onClick={() => input.current?.click()}
        className="rounded-lg bg-neutral-900 px-5 py-3 font-semibold text-white dark:bg-neutral-100 dark:text-neutral-900"
      >
        {t('choose')}
      </button>
      <p className="mt-2 text-sm text-neutral-500">{t('dropHere')}</p>
    </div>
  );
}

function DetailsEditor({
  value,
  onChange,
  scholars,
  topics,
  withSource = false,
}: {
  value: Details;
  onChange: (patch: Partial<Details>) => void;
  scholars: ScholarItem[];
  topics: TopicItem[];
  withSource?: boolean;
}) {
  const t = useTranslations('upload');
  const locale = useLocale();
  const [other, setOther] = useState(value.scholarId === null && value.scholarOther !== '');
  const name = (s: { name_ar: string; name_en: string }) => (locale === 'ar' ? s.name_ar : s.name_en);
  const sorted = useMemo(
    () => [...scholars].sort((a, b) => name(a).localeCompare(name(b), locale)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [scholars, locale],
  );
  const confidences: [Confidence, string][] = [
    ['confirmed', t('confidenceConfirmed')],
    ['probably', t('confidenceProbably')],
    ['not_sure', t('confidenceNotSure')],
  ];

  return (
    <div className="space-y-4">
      <label className="block">
        <span className="mb-1 block text-sm font-semibold">{t('scholar')}</span>
        <select
          className="w-full rounded-md border border-neutral-300 bg-transparent px-3 py-2 dark:border-neutral-700"
          value={value.scholarId ?? (other ? '__other' : '')}
          onChange={(e) => {
            const v = e.target.value;
            setOther(v === '__other');
            onChange(v === '__other' || v === '' ? { scholarId: null } : { scholarId: v, scholarOther: '' });
          }}
        >
          <option value="">{t('scholarChoose')}</option>
          {sorted.map((s) => (
            <option key={s.id} value={s.id}>
              {name(s)}
            </option>
          ))}
          <option value="__other">{t('scholarOther')}</option>
        </select>
      </label>
      {other && (
        <label className="block">
          <span className="mb-1 block text-sm font-semibold">{t('scholarOtherName')}</span>
          <input
            className="w-full rounded-md border border-neutral-300 bg-transparent px-3 py-2 dark:border-neutral-700"
            value={value.scholarOther}
            onChange={(e) => onChange({ scholarOther: e.target.value })}
          />
        </label>
      )}

      <fieldset>
        <legend className="mb-1 text-sm font-semibold">{t('confidence')}</legend>
        <div className="space-y-1">
          {confidences.map(([v, label]) => (
            <label key={v} className="flex items-center gap-2">
              <input type="radio" checked={value.confidence === v} onChange={() => onChange({ confidence: v })} />
              <span>{label}</span>
            </label>
          ))}
        </div>
        <p className="mt-2 text-xs text-neutral-600 dark:text-neutral-400">{t('confidenceNote')}</p>
      </fieldset>

      <label className="block">
        <span className="mb-1 block text-sm font-semibold">{t('topic')}</span>
        <select
          className="w-full rounded-md border border-neutral-300 bg-transparent px-3 py-2 dark:border-neutral-700"
          value={value.topicId ?? ''}
          onChange={(e) => onChange({ topicId: e.target.value || null })}
        >
          <option value="">{t('topicNone')}</option>
          {topics.map((main) => (
            <optgroup key={main.id} label={name(main)}>
              <option value={main.id}>{name(main)}</option>
              {main.children.map((sub) => (
                <option key={sub.id} value={sub.id}>
                  {name(sub)}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </label>

      {withSource && (
        <label className="block">
          <span className="mb-1 block text-sm font-semibold">{t('source')}</span>
          <input
            className="w-full rounded-md border border-neutral-300 bg-transparent px-3 py-2 dark:border-neutral-700"
            value={value.sourceNote}
            placeholder={t('sourcePlaceholder')}
            onChange={(e) => onChange({ sourceNote: e.target.value })}
          />
        </label>
      )}
    </div>
  );
}

function FileRow({
  row,
  file,
  uploadKey,
  defaults,
  scholars,
  topics,
  onChoose,
  onOverride,
  onRemove,
  onRetry,
}: {
  row: Row;
  file: File | undefined;
  uploadKey: string;
  defaults: Details;
  scholars: ScholarItem[];
  topics: TopicItem[];
  onChoose: (choice: 'keep' | 'drop') => void;
  onOverride: (patch: Partial<Details>) => void;
  onRemove: () => void;
  onRetry: () => void;
}) {
  const t = useTranslations('upload');
  const [showMine, setShowMine] = useState(false);
  const [editing, setEditing] = useState(false);
  const mine = useMemo(() => (showMine && file ? URL.createObjectURL(file) : null), [showMine, file]);
  useEffect(() => () => {
    if (mine) URL.revokeObjectURL(mine);
  }, [mine]);

  const check = row.check;
  const isCandidate = row.phase === 'checked' && check?.status === 'candidates';
  const keeps = row.phase === 'checked' && (check?.status === 'new' || (isCandidate && row.choice === 'keep'));

  let status: string;
  if (row.phase === 'uploading') status = t('status.uploading', { percent: Math.round(row.progress * 100) });
  else if (row.phase === 'checked' && check) {
    status =
      check.status === 'rejected'
        ? t(check.duplicate_of?.pending ? 'status.rejectedPending' : 'status.rejected')
        : t(`status.${check.status}`);
  } else if (row.phase === 'failed') status = '';
  else status = t(`status.${row.phase}`);

  const tone =
    row.phase === 'failed'
      ? 'border-red-300 dark:border-red-800'
      : isCandidate && row.choice === null
        ? 'border-amber-400 dark:border-amber-700'
        : 'border-neutral-200 dark:border-neutral-800';

  return (
    <li className={`space-y-3 rounded-xl border p-4 ${tone}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-semibold" dir="auto">
            {row.name}
          </p>
          <p className="text-xs text-neutral-500">
            <bdi>{megabytes(row.size)}</bdi>
          </p>
        </div>
        {!['sending', 'sent', 'dropped'].includes(row.phase) && (
          <button type="button" onClick={onRemove} className="shrink-0 text-sm text-neutral-500 underline">
            {t('remove')}
          </button>
        )}
      </div>

      {row.phase === 'uploading' && (
        <div className="h-2 overflow-hidden rounded bg-neutral-200 dark:bg-neutral-800">
          <div className="h-full bg-emerald-600 transition-all" style={{ inlineSize: `${Math.round(row.progress * 100)}%` }} />
        </div>
      )}
      {status && <p className="text-sm">{status}</p>}
      {row.error && (
        <div className="flex items-center gap-3 text-sm text-red-700 dark:text-red-300">
          <span>{t.has(`error.${row.error}`) ? t(`error.${row.error}`) : t('error.other', { code: row.error })}</span>
          {row.phase === 'failed' && ['network', 'http_502', 'http_503', 'http_504'].includes(row.error) && (
            <button type="button" onClick={onRetry} className="underline">
              {t('retry')}
            </button>
          )}
        </div>
      )}

      {file && (
        <div>
          <button type="button" onClick={() => setShowMine((s) => !s)} className="text-sm underline">
            {t('playMine')}
          </button>
          {mine && <video controls playsInline src={mine} className="mt-2 max-h-64 w-full rounded-md bg-black" />}
        </div>
      )}

      {isCandidate && check && (
        <div className="space-y-3 rounded-lg bg-amber-50 p-3 dark:bg-amber-950">
          {check.candidates.slice(0, 3).map((match, i) => (
            <Candidate key={i} match={match} uploadKey={uploadKey} />
          ))}
          <div className="flex flex-col gap-2 sm:flex-row">
            {(['drop', 'keep'] as const).map((choice) => (
              <button
                key={choice}
                type="button"
                onClick={() => onChoose(choice)}
                aria-pressed={row.choice === choice}
                className={`flex-1 rounded-md border px-3 py-2 text-sm font-semibold ${row.choice === choice ? 'border-emerald-700 bg-emerald-700 text-white' : 'border-neutral-400 bg-white dark:bg-neutral-900'}`}
              >
                {t(choice === 'drop' ? 'candidate.same' : 'candidate.different')}
              </button>
            ))}
          </div>
        </div>
      )}

      {keeps && (
        <div>
          <button type="button" onClick={() => setEditing((e) => !e)} className="text-sm underline">
            {t('perFile')}
          </button>
          {editing && (
            <div className="mt-3 border-s-2 border-neutral-300 ps-3 dark:border-neutral-700">
              <DetailsEditor
                value={effectiveDetails(row, defaults)}
                onChange={onOverride}
                scholars={scholars}
                topics={topics}
              />
            </div>
          )}
        </div>
      )}
    </li>
  );
}

function Candidate({ match, uploadKey }: { match: MatchOut; uploadKey: string }) {
  const t = useTranslations('upload');
  const locale = useLocale();
  const scholar = match.scholar ? (locale === 'ar' ? match.scholar.name_ar : match.scholar.name_en) : null;
  const title = locale === 'ar' ? (match.title_ar ?? match.title_en) : (match.title_en ?? match.title_ar);

  return (
    <div className="space-y-2">
      {match.public ? (
        <p className="text-sm">
          <span className="font-semibold">{scholar}</span>
          {title && (
            <>
              {' — '}
              <span lang={match.title_ar && title === match.title_ar ? 'ar' : undefined} dir="auto" className="font-text">
                {title}
              </span>
            </>
          )}
        </p>
      ) : (
        <p className="text-sm">{t(match.pending ? 'candidate.pending' : 'candidate.withheld')}</p>
      )}
      {match.overlap_ms !== null && (
        <p className="text-xs text-neutral-600 dark:text-neutral-400">
          {t('candidate.matches', { duration: formatDuration(match.overlap_ms) })}
        </p>
      )}
      {match.preview_id && (
        <video
          controls
          playsInline
          preload="metadata"
          src={mediaUrl(match.preview_id, uploadKey)}
          className="max-h-64 w-full rounded-md bg-black"
        />
      )}
      {match.source_url && (
        <a href={match.source_url} target="_blank" rel="noopener noreferrer" className="text-sm underline">
          {t('candidate.openSource')}
        </a>
      )}
    </div>
  );
}
