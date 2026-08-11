import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import packageMetadata from './package.json';

const explicitRelease = process.env.VITE_SENTRY_RELEASE?.trim();
const buildCommit = (
  process.env.VITE_GIT_COMMIT_SHA
  || process.env.VERCEL_GIT_COMMIT_SHA
  || process.env.RENDER_GIT_COMMIT
  || process.env.GITHUB_SHA
  || ''
).trim();
const release = explicitRelease || (buildCommit ? `admitly-admin@${buildCommit}` : `admitly-admin@${packageMetadata.version}`);
const distribution = process.env.VITE_SENTRY_DIST?.trim() || (buildCommit ? buildCommit.slice(0, 12) : 'web');

export default defineConfig({
  plugins: [react()],
  define: {
    __ADMITLY_RELEASE__: JSON.stringify(release),
    __ADMITLY_DIST__: JSON.stringify(distribution),
  },
});
