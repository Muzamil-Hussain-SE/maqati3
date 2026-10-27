'use client';

import { useLocale, useTranslations } from 'next-intl';
import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import {
  AdminError,
  addScholar,
  discardItem,
  fetchItems,
  fetchMe,
  fetchScholars,
  mediaUrl,
  registerItem,
  signOut,
  type Me,
} from '@/lib/admin/api';
import {
  canRegister,
  errorKey,
  groupItems,
  loginResult,
  loginUrl,
  scholarLabel,
  slugFrom,
  type Item,
  type Scholar,
} from '@/lib/admin/logic';
import { formatDuration } from '@/lib/uploads/batch';

type View =
  | { kind: 'loading' }
  | { kind: 'signedOut' }
  | { kind: 'notConfigured' }
  | { kind: 'failed'; code: string }
  | { kind: 'ready'; me: Me };

function subscribeToLocation(onChange: () => void): () => void {
  window.addEventListener('popstate', onChange);
  return () => window.removeEventListener('popstate', onChange);
}

function codeOf(error: unknown): string {
  return error instanceof AdminError ? error.code : 'network';
}

const BUTTON =
  'rounded-md px-4 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50';
const PRIMARY = `${BUTTON} bg-emerald-700 text-white`;
const SECONDARY = `${BUTTON} border border-neutral-400 bg-transparent`;
const FIELD =
  'w-full rounded-md border border-neutral-300 bg-transparent px-3 py-2 dark:border-neutral-700';

export default function AdminDashboard() {
  const t = useTranslations('admin');
  const [view, setView] = useState<View>({ kind: 'loading' });
  const [items, setItems] = useState<Item[]>([]);
  const [scholars, setScholars] = useState<Scholar[]>([]);
  const search = useSyncExternalStore(
    subscribeToLocation,
    () => window.location.search,
    () => '',
  );
  const result = loginResult(search);

  const reload = useCallback(async () => {
    const [list, people] = await Promise.all([fetchItems(), fetchScholars()]);
    setItems(list);
    setScholars(people);
  }, []);

  useEffect(() => {
    fetchMe()
      .then(async (me) => {
        await reload();
        setView({ kind: 'ready', me });
      })
      .catch((error: unknown) => {
        const code = codeOf(error);
        if (code === 'admin_login_required') setView({ kind: 'signedOut' });
        else if (code === 'admin_not_configured') setView({ kind: 'notConfigured' });
        else setView({ kind: 'failed', code });
      });
  }, [reload]);

  if (view.kind === 'loading') return <p>{t('loading')}</p>;
  if (view.kind === 'notConfigured') return <Notice>{t('notConfigured')}</Notice>;
  if (view.kind === 'failed') return <Notice>{t(`error.${errorKey(view.code)}`)}</Notice>;
  if (view.kind === 'signedOut') return <SignedOut denied={result} />;

  const { waiting, registered } = groupItems(items);
  return (
    <div className="space-y-10">
      <div className="flex items-center justify-between gap-4 text-sm">
        <span>
          {t('signedInAs', { email: view.me.email })}
        </span>
        <button
          type="button"
          className={SECONDARY}
          onClick={() =>
            signOut().then(
              () => setView({ kind: 'signedOut' }),
              () => setView({ kind: 'signedOut' }),
            )
          }
        >
          {t('signOut')}
        </button>
      </div>

      <section className="space-y-4">
        <h2 className="text-xl font-semibold">{t('waiting.title', { count: waiting.length })}</h2>
        {waiting.length === 0 && <p className="text-neutral-600">{t('waiting.empty')}</p>}
        <ul className="space-y-4">
          {waiting.map((item) => (
            <WaitingCard
              key={item.sha256}
              item={item}
              scholars={scholars}
              onChanged={reload}
              onScholarAdded={(s) => setScholars((current) => [...current, { ...s }])}
            />
          ))}
        </ul>
      </section>

      <section className="space-y-4">
        <h2 className="text-xl font-semibold">
          {t('registered.title', { count: registered.length })}
        </h2>
        {registered.length === 0 && <p className="text-neutral-600">{t('registered.empty')}</p>}
        <ul className="space-y-4">
          {registered.map((item) => (
            <RegisteredCard key={item.sha256} item={item} />
          ))}
        </ul>
      </section>
    </div>
  );
}

function Notice({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-lg bg-amber-50 p-4 text-amber-900 dark:bg-amber-950 dark:text-amber-100">
      {children}
    </p>
  );
}

function SignedOut({ denied }: { denied: 'denied' | 'failed' | null }) {
  const t = useTranslations('admin');
  const locale = useLocale();
  return (
    <div className="space-y-4">
      {denied && <Notice>{t(`login.${denied}`)}</Notice>}
      <p className="text-neutral-600 dark:text-neutral-400">{t('signedOutHint')}</p>
      <a href={loginUrl(locale)} className={`${PRIMARY} inline-block`}>
        {t('signIn')}
      </a>
    </div>
  );
}

function Meta({ item }: { item: Item }) {
  const t = useTranslations('admin');
  const locale = useLocale();
  const received = useMemo(
    () =>
      new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(
        new Date(item.received_at),
      ),
    [item.received_at, locale],
  );
  return (
    <div className="space-y-1">
      <p className="font-semibold" dir="auto">
        <bdi>{item.original_name}</bdi>
      </p>
      <p className="text-sm text-neutral-600 dark:text-neutral-400">
        <bdi>{formatDuration(item.duration_ms)}</bdi> · {received}
        {item.contributor && <> · {t('from', { name: item.contributor })}</>}
      </p>
    </div>
  );
}

function Player({ sha256 }: { sha256: string }) {
  return (
    <video
      controls
      playsInline
      preload="metadata"
      src={mediaUrl(sha256)}
      className="max-h-80 w-full rounded-md bg-black"
    />
  );
}

function WaitingCard({
  item,
  scholars,
  onChanged,
  onScholarAdded,
}: {
  item: Item;
  scholars: Scholar[];
  onChanged: () => Promise<void>;
  onScholarAdded: (scholar: Scholar) => void;
}) {
  const t = useTranslations('admin');
  const locale = useLocale();
  const [chosen, setChosen] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const sorted = useMemo(
    () =>
      [...scholars].sort((a, b) =>
        scholarLabel(a, locale).localeCompare(scholarLabel(b, locale), locale),
      ),
    [scholars, locale],
  );

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      await onChanged();
    } catch (failure) {
      const code = codeOf(failure);
      setError(code);
      // Someone else got there first: show the list as it is now.
      if (code === 'not_waiting') await onChanged().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="space-y-4 rounded-xl border border-neutral-200 p-4 dark:border-neutral-800">
      <Meta item={item} />
      <Player sha256={item.sha256} />

      {item.kept_despite.length > 0 && (
        <div className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-100">
          <p className="font-semibold">{t('keptDespite')}</p>
          <ul className="list-inside list-disc">
            {item.kept_despite.map((match) => (
              <li key={match}>
                <bdi>{match}</bdi>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="space-y-3">
        <label className="block">
          <span className="mb-1 block text-sm font-semibold">{t('scholar.label')}</span>
          <select
            className={FIELD}
            value={chosen}
            onChange={(e) => {
              if (e.target.value === '__add') setAdding(true);
              else setChosen(e.target.value);
            }}
          >
            <option value="">{t('scholar.choose')}</option>
            {sorted.map((s) => (
              <option key={s.id} value={s.id}>
                {scholarLabel(s, locale)}
              </option>
            ))}
            <option value="__add">{t('scholar.add')}</option>
          </select>
        </label>
        {adding && (
          <NewScholar
            onCancel={() => setAdding(false)}
            onAdded={(scholar) => {
              onScholarAdded(scholar);
              setChosen(scholar.id);
              setAdding(false);
            }}
          />
        )}
        <p className="text-xs text-neutral-600 dark:text-neutral-400">{t('scholar.unclear')}</p>
      </div>

      {error && <p className="text-sm text-red-700 dark:text-red-300">{t(`error.${errorKey(error)}`)}</p>}

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className={PRIMARY}
          disabled={!canRegister(chosen, busy)}
          onClick={() => run(() => registerItem(item.sha256, chosen))}
        >
          {busy ? t('working') : t('register')}
        </button>
        <button
          type="button"
          className={SECONDARY}
          disabled={busy}
          onClick={() => {
            if (window.confirm(t('discardConfirm'))) run(() => discardItem(item.sha256));
          }}
        >
          {t('discard')}
        </button>
        <span className="text-xs text-neutral-600 dark:text-neutral-400">{t('registerHint')}</span>
      </div>
    </li>
  );
}

function NewScholar({
  onAdded,
  onCancel,
}: {
  onAdded: (scholar: Scholar) => void;
  onCancel: () => void;
}) {
  const t = useTranslations('admin');
  const [nameEn, setNameEn] = useState('');
  const [nameAr, setNameAr] = useState('');
  const [id, setId] = useState('');
  const [idTouched, setIdTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const shownId = idTouched ? id : slugFrom(nameEn);
  const ready = shownId !== '' && nameEn.trim() !== '' && nameAr.trim() !== '' && !busy;

  async function save() {
    setBusy(true);
    setError(null);
    try {
      onAdded(await addScholar({ id: shownId, name_en: nameEn.trim(), name_ar: nameAr.trim() }));
    } catch (failure) {
      setError(codeOf(failure));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-neutral-300 p-3 dark:border-neutral-700">
      <label className="block">
        <span className="mb-1 block text-sm font-semibold">{t('scholar.nameEnLabel')}</span>
        <input className={FIELD} value={nameEn} onChange={(e) => setNameEn(e.target.value)} dir="ltr" />
      </label>
      <label className="block">
        <span className="mb-1 block text-sm font-semibold">{t('scholar.nameArLabel')}</span>
        <input className={FIELD} value={nameAr} onChange={(e) => setNameAr(e.target.value)} dir="rtl" />
      </label>
      <label className="block">
        <span className="mb-1 block text-sm font-semibold">{t('scholar.idLabel')}</span>
        <input
          className={FIELD}
          value={shownId}
          dir="ltr"
          onChange={(e) => {
            setIdTouched(true);
            setId(e.target.value);
          }}
        />
      </label>
      {error && <p className="text-sm text-red-700 dark:text-red-300">{t(`error.${errorKey(error)}`)}</p>}
      <div className="flex gap-3">
        <button type="button" className={PRIMARY} disabled={!ready} onClick={save}>
          {t('scholar.save')}
        </button>
        <button type="button" className={SECONDARY} onClick={onCancel}>
          {t('scholar.cancel')}
        </button>
      </div>
    </div>
  );
}

function RegisteredCard({ item }: { item: Item }) {
  const t = useTranslations('admin');
  const locale = useLocale();
  const [open, setOpen] = useState(false);
  return (
    <li className="space-y-3 rounded-xl border border-neutral-200 p-4 dark:border-neutral-800">
      <Meta item={item} />
      {item.entry && (
        <p className="text-sm">
          <span className="font-semibold">{scholarLabel(item.entry.scholar, locale)}</span>
          {' · '}
          {t('entry', { id: item.entry.entry_id })}
          {item.registered_by && <> · {t('registeredBy', { email: item.registered_by })}</>}
        </p>
      )}
      <button type="button" className="text-sm underline" onClick={() => setOpen((o) => !o)}>
        {open ? '▲' : '▶'} {t('play')}
      </button>
      {open && <Player sha256={item.sha256} />}
    </li>
  );
}
