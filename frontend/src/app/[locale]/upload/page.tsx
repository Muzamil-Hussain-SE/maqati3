import type { Metadata } from 'next';
import { getTranslations, setRequestLocale } from 'next-intl/server';
import UploadBatch from './UploadBatch';

// Reached only through the unlisted link the admin hands out; never in a search index.
export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: 'upload' });
  return { title: t('title'), robots: { index: false, follow: false } };
}

export default async function UploadPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations('upload');

  return (
    <main className="mx-auto max-w-3xl space-y-6 px-4 py-10">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold">{t('title')}</h1>
        <p className="text-neutral-600 dark:text-neutral-400">{t('intro')}</p>
      </header>
      <UploadBatch />
    </main>
  );
}
