import type { Metadata } from 'next';
import { getTranslations, setRequestLocale } from 'next-intl/server';
import AdminDashboard from './AdminDashboard';

// For the admins only; never in a search index.
export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: 'admin' });
  return { title: t('title'), robots: { index: false, follow: false } };
}

export default async function AdminPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations('admin');

  return (
    <main className="mx-auto max-w-4xl space-y-6 px-4 py-10">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold">{t('title')}</h1>
        <p className="text-neutral-600 dark:text-neutral-400">{t('intro')}</p>
      </header>
      <AdminDashboard />
    </main>
  );
}
