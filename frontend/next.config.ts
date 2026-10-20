import type { NextConfig } from 'next';
import createNextIntlPlugin from 'next-intl/plugin';

const withNextIntl = createNextIntlPlugin('./src/i18n/request.ts');

const nextConfig: NextConfig = {
  // 3,000 entries across 3 locales is 9,000 pages — pre-renderable. 30,000 is not.
  // Deciding the top-N boundary now avoids a painful rewrite later; see CLAUDE.md.
  experimental: {},
};

export default withNextIntl(nextConfig);
