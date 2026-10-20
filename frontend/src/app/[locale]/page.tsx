import { getTranslations, setRequestLocale } from 'next-intl/server';

export default async function Home({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations('site');

  return (
    <main className="mx-auto max-w-2xl px-4 py-16">
      <h1 className="font-text text-4xl font-semibold">{t('name')}</h1>
      <p className="mt-4 text-lg text-neutral-600 dark:text-neutral-400">{t('tagline')}</p>
    </main>
  );
}
