const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const repositoryRoot = path.resolve(root, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');

const router = read('src/app/router.tsx');
const publicSite = read('src/components/PublicSite.tsx');
const landing = read('src/pages/LandingPage.tsx');
const mobileNavigator = fs.readFileSync(
  path.join(repositoryRoot, 'mobile/src/navigation/RootNavigator.tsx'),
  'utf8',
);

test('root, discovery, detail, and legal routes are public', () => {
  assert.match(router, /<Route index element={<LandingPage\s*\/>}/);
  assert.match(router, /<Route path="\/events" element={<EventsPage\s*\/>}/);
  assert.match(router, /<Route path="\/events\/:eventId" element={<EventDetailPage\s*\/>}/);
  for (const route of ['/privacy', '/refund-policy', '/terms', '/organizer-terms', '/buyer-terms']) {
    assert.match(router, new RegExp(`<Route path="${route.replace('/', '\\/')}"`));
    assert.ok(router.indexOf(`path="${route}"`) < router.indexOf('<Route element={<RequireAdmin />}'));
  }
});

test('attendee actions use registered mobile auth deep links, not admin auth', () => {
  assert.match(publicSite, /attendeeLoginUrl = 'admitly:\/\/sign-in'/);
  assert.match(publicSite, /attendeeSignupUrl = 'admitly:\/\/sign-up'/);
  assert.match(mobileNavigator, /SignIn: 'sign-in'/);
  assert.match(mobileNavigator, /SignUp: 'sign-up'/);
  assert.match(landing, /to="\/events"/);
  assert.match(landing, /href={attendeeLoginUrl}>Create an Event/);
});

test('sensitive and recovery routes remain wired as before', () => {
  assert.match(router, /<Route path="\/login" element={<LoginPage\s*\/>}/);
  assert.match(router, /<Route path="\/reset-password" element={<ResetPasswordRedirectPage\s*\/>}/);
  assert.match(router, /<Route path="\/verify-email" element={<VerifyEmailRedirectPage\s*\/>}/);
  for (const route of ['/support', '/finance', '/check-in', '/integrations', '/messaging', '/event-approvals']) {
    assert.ok(router.indexOf(`path="${route}"`) > router.indexOf('<Route element={<RequireAdmin />}'));
  }
});

test('footer exposes every required public policy', () => {
  assert.ok(publicSite.includes('to="/terms#questions"'));
  for (const [route, label] of [
    ['/privacy', 'Privacy Policy'],
    ['/refund-policy', 'Refund Policy'],
    ['/terms', 'Terms of Service'],
    ['/organizer-terms', 'Organizer Terms'],
    ['/buyer-terms', 'Buyer Terms'],
  ]) {
    assert.ok(publicSite.includes(`to="${route}"`));
    assert.ok(publicSite.includes(`>${label}</Link>`));
  }
});
