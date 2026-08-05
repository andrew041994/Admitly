const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const client = fs.readFileSync(path.join(__dirname, 'client.ts'), 'utf8');
const session = fs.readFileSync(path.join(__dirname, '..', 'context', 'SessionContext.tsx'), 'utf8');

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
