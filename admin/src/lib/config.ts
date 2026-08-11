import packageMetadata from '../../package.json';

const DEFAULT_API_BASE_URL = 'https://admitly.onrender.com';
const buildCommit = (import.meta.env.VITE_GIT_COMMIT_SHA as string | undefined)?.trim() || '';

export const apiBaseUrl =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || DEFAULT_API_BASE_URL;

export const sentryDsn = (import.meta.env.VITE_SENTRY_DSN as string | undefined)?.trim() || '';
export const sentryEnvironment =
  (import.meta.env.VITE_SENTRY_ENVIRONMENT as string | undefined)?.trim() || import.meta.env.MODE;
export const sentryRelease =
  import.meta.env.VITE_ADMITLY_RELEASE?.trim()
  || (import.meta.env.VITE_SENTRY_RELEASE as string | undefined)?.trim()
  || (buildCommit ? `admitly-admin@${buildCommit}` : '')
  || `admitly-admin@${packageMetadata.version}`;
export const sentryDist =
  import.meta.env.VITE_ADMITLY_DIST?.trim()
  || (import.meta.env.VITE_SENTRY_DIST as string | undefined)?.trim()
  || (buildCommit ? buildCommit.slice(0, 12) : '')
  || 'web';
