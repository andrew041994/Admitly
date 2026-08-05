const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const screen = fs.readFileSync(path.join(__dirname, 'NotificationsScreen.tsx'), 'utf8');
const home = fs.readFileSync(path.join(__dirname, 'HomeScreen.tsx'), 'utf8');
const root = fs.readFileSync(path.join(__dirname, '..', 'RootNavigator.tsx'), 'utf8');
const push = fs.readFileSync(path.join(__dirname, '..', '..', 'features', 'notifications', 'pushRegistration.ts'), 'utf8');

test('authenticated home exposes an accessible bell with capped unread badge', () => {
  assert.match(home, /accessibilityLabel=\{`Notifications/);
  assert.match(home, /unreadCount > 99 \? '99\+' : unreadCount/);
  assert.match(home, /getUnreadNotificationCount/);
  assert.match(root, /name="Notifications"/);
});

test('inbox supports empty, loading, refresh, read, and mark-all states', () => {
  assert.match(screen, /RefreshControl/);
  assert.match(screen, /markNotificationRead/);
  assert.match(screen, /markAllNotificationsRead/);
  assert.match(screen, /You’re all caught up/);
  assert.match(screen, /ActivityIndicator/);
  assert.match(screen, /onEndReached=\{\(\) => void loadMore\(\)\}/);
});

test('permission denial is optional and nearby location is explicit opt-in', () => {
  assert.match(screen, /Enable push notifications/);
  assert.match(screen, /Permission was not granted\. You can continue using the in-app inbox/);
  assert.match(screen, /requestForegroundPermissionsAsync/);
  assert.match(screen, /Nearby alerts remain off/);
  assert.match(push, /if \(!permission\.granted\) return false/);
});

test('push responses use the allowlisted route mapper and logout disables this installation', () => {
  assert.match(root, /getNotificationDestination/);
  assert.match(root, /addNotificationResponseReceivedListener/);
  assert.match(push, /disableDevicePushToken/);
  assert.match(push, /installation_id/);
});
