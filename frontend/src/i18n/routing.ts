import { defineRouting } from 'next-intl/routing';

/**
 * Arabic is the source language of every recording, but English is the default UI
 * locale: most contributors and most visitors arriving from outside the Arabic-speaking
 * world read English. Arabic is never a fallback — it is the original.
 */
export const routing = defineRouting({
  locales: ['en', 'ar', 'de'],
  defaultLocale: 'en',
  localePrefix: 'always',
});

export type Locale = (typeof routing.locales)[number];

/** Script direction per locale. Used for the <html dir> attribute. */
export const direction: Record<Locale, 'ltr' | 'rtl'> = {
  en: 'ltr',
  de: 'ltr',
  ar: 'rtl',
};
