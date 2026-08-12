const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const client = fs.readFileSync(path.join(__dirname, 'client.ts'), 'utf8');
const session = fs.readFileSync(path.join(__dirname, '..', 'context', 'SessionContext.tsx'), 'utf8');
const auth = fs.readFileSync(path.join(__dirname, 'auth.ts'), 'utf8');
const profile = fs.readFileSync(path.join(__dirname, '..', 'navigation', 'screens', 'ProfileScreen.tsx'), 'utf8');

test('mobile API identity is supplied only by the session Bearer token', () => {
  assert.match(client, /requestHeaders\.set\('Authorization', `Bearer \$\{authToken\}`\)/);
  assert.doesNotMatch(client, /x-user-id|x_user_id/i);
  assert.ok(
    client.indexOf("new Headers(headers)") < client.indexOf("requestHeaders.set('Authorization'"),
    'the session token must override any feature-supplied Authorization header',
  );
});

test('session refresh and verification routing remain present', () => {
  assert.match(session, /refresh\(storedSession\.refreshToken\)/);
  assert.match(session, /getCurrentUser\(\)/);
  assert.doesNotMatch(session, /x-user-id|x_user_id/i);
});

test('rotated sessions replace SecureStore and revoking logout remains failure-safe', () => {
  assert.match(session, /setStoredSession\(toStoredSession\(refreshed\.tokens\)\)/);
  assert.match(session, /logout\(storedSession\?\.refreshToken \?\? null\)/);
  const signOutBlock = session.slice(session.indexOf('signOut: async () =>'), session.indexOf('signOutAll: async () =>'));
  assert.ok(signOutBlock.indexOf('await logout(storedSession?.refreshToken ?? null)') < signOutBlock.indexOf('await clearStoredSession()'));
  assert.match(session, /Server failure must not retain local credentials/);
  assert.match(auth, /path: '\/auth\/logout-all'/);
  assert.match(profile, /Log out all devices/);
  assert.match(session, /error instanceof ApiError && error\.status === 401/);
  assert.match(session, /await logoutAll\(\)/);
});

test('a revoked session returns mobile to signed-out state', () => {
  assert.match(client, /response\.status === 401 && authToken && unauthorizedHandler/);
  assert.match(session, /setApiUnauthorizedHandler/);
  assert.match(session, /setState\('signedOut'\)/);
});

test('mobile exposes account-level creator verification without an ID upload path', () => {
  const account = fs.readFileSync(path.join(__dirname, 'account.ts'), 'utf8');
  const createEvent = fs.readFileSync(path.join(__dirname, '..', 'navigation', 'screens', 'CreateEventScreen.tsx'), 'utf8');
  assert.match(account, /creator_age_identity_verification_status/);
  assert.match(profile, /You do not need to submit ID again for future events/);
  assert.match(profile, /not uploaded in the app/);
  assert.doesNotMatch(profile, /ImagePicker|uploadEventCoverImage/);
  assert.doesNotMatch(createEvent, /government|identity document|date of birth|document number/i);
});
