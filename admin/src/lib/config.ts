const DEFAULT_API_BASE_URL = 'https://admitly.onrender.com';

export const apiBaseUrl =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || DEFAULT_API_BASE_URL;

export const sentryDsn = (import.meta.env.VITE_SENTRY_DSN as string | undefined)?.trim() || '';
export const sentryEnvironment =
  (import.meta.env.VITE_SENTRY_ENVIRONMENT as string | undefined)?.trim() || import.meta.env.MODE;
export const sentryRelease = __ADMITLY_RELEASE__;
export const sentryDist = __ADMITLY_DIST__;
