const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const envSource = fs.readFileSync(path.join(__dirname, 'env.ts'), 'utf8');
const appSource = fs.readFileSync(path.join(__dirname, '..', 'App.tsx'), 'utf8');

test('mobile Sentry uses explicit release then application metadata fallback', () => {
  assert.match(envSource, /EXPO_PUBLIC_SENTRY_RELEASE/);
  assert.match(envSource, /com\.admitly\.app@\$\{applicationVersion\}/);
  assert.match(envSource, /buildNumber/);
  assert.match(envSource, /versionCode/);
  assert.match(envSource, /expoRuntimeVersion/);
});

test('mobile Sentry remains conditional and receives environment release and distribution', () => {
  assert.match(appSource, /if \(env\.sentryDsn\)/);
  assert.match(appSource, /environment: env\.sentryEnvironment/);
  assert.match(appSource, /release: env\.sentryRelease/);
  assert.match(appSource, /dist: env\.sentryDist \|\| undefined/);
});
