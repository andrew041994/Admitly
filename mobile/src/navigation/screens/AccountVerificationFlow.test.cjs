const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const read = (name) => fs.readFileSync(path.join(__dirname, name), 'utf8');
const signup = read('SignUpScreen.tsx');
const profile = read('ProfileScreen.tsx');
const verify = read('VerifyEmailScreen.tsx');
const root = fs.readFileSync(path.join(__dirname, '..', 'RootNavigator.tsx'), 'utf8');
const session = fs.readFileSync(path.join(__dirname, '..', '..', 'context', 'SessionContext.tsx'), 'utf8');

test('signup and profile contain no phone collection or missing-phone prompts', () => {
  assert.doesNotMatch(signup, /phone|telephone|normalizePhone/i);
  assert.doesNotMatch(profile, /phone|telephone|normalizePhone|complete profile/i);
  assert.match(signup, /normalizeEmailAddress/);
  assert.match(signup, /Enter a valid email address/);
});

test('new unverified sessions are routed to the dedicated verification screen', () => {
  assert.match(root, /user\?\.requires_email_verification/);
  assert.match(root, /<AuthNavigator verificationOnly/);
  assert.match(root, /path: 'verify-email'/);
  assert.match(root, /path: 'reset-password'/);
});

test('verification supports success refresh, expired recovery, and duplicate-safe resend', () => {
  assert.match(verify, /if \(resending\) return/);
  assert.match(verify, /Resend verification email/);
  assert.match(verify, /Request a new verification email and try again/);
  assert.match(session, /const refreshedUser = await getCurrentUser\(\)/);
  assert.match(session, /setUser\(refreshedUser\)/);
});
