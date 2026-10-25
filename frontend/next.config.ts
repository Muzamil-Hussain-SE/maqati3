import type { NextConfig } from 'next';
import createNextIntlPlugin from 'next-intl/plugin';

const withNextIntl = createNextIntlPlugin('./src/i18n/request.ts');

const nextConfig: NextConfig = {
  // 3,000 entries across 3 locales is 9,000 pages — pre-renderable. 30,000 is not.
  // Deciding the top-N boundary now avoids a painful rewrite later; see CLAUDE.md.
  experimental: {},
  // Tailwind v4 runs as a Turbopack loader. Without this rule the stylesheet ships with
  // its @theme and @import directives unprocessed and no utility class exists at all.
  turbopack: {
    rules: {
      '*.css': { loaders: ['@tailwindcss/turbopack'], as: '*.css' },
    },
  },
  // The API lives on the same origin. In production Caddy sends /api straight to the
  // backend; in development this rewrite does, so the browser never needs CORS.
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.API_ORIGIN ?? 'http://127.0.0.1:8000'}/api/:path*`,
      },
    ];
  },
};

export default withNextIntl(nextConfig);
