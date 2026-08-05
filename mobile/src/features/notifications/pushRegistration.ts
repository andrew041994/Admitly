import Constants from 'expo-constants';
import * as Notifications from 'expo-notifications';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

import { disableDevicePushToken, registerDevicePushToken } from '../../api/notifications';

const INSTALLATION_KEY = 'admitly.push.installation-id';
const TOKEN_KEY = 'admitly.push.expo-token';

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

function createInstallationId() {
  return `install-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
}

async function getInstallationId() {
  const existing = await SecureStore.getItemAsync(INSTALLATION_KEY);
  if (existing) return existing;
  const created = createInstallationId();
  await SecureStore.setItemAsync(INSTALLATION_KEY, created);
  return created;
}

async function registerGrantedToken() {
  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync('default', {
      name: 'Admitly alerts',
      importance: Notifications.AndroidImportance.DEFAULT,
    });
  }
  const projectId = Constants.expoConfig?.extra?.eas?.projectId ?? Constants.easConfig?.projectId;
  if (!projectId) throw new Error('Push notification project configuration is unavailable.');
  const result = await Notifications.getExpoPushTokenAsync({ projectId });
  const installationId = await getInstallationId();
  await registerDevicePushToken({
    token: result.data,
    platform: Platform.OS === 'ios' ? 'ios' : 'android',
    installation_id: installationId,
  });
  await SecureStore.setItemAsync(TOKEN_KEY, result.data);
  return result.data;
}

export async function registerPushTokenIfPermitted() {
  const permission = await Notifications.getPermissionsAsync();
  if (!permission.granted) return false;
  await registerGrantedToken();
  return true;
}

export async function requestAndRegisterPushToken() {
  let permission = await Notifications.getPermissionsAsync();
  if (!permission.granted && permission.canAskAgain) {
    permission = await Notifications.requestPermissionsAsync();
  }
  if (!permission.granted) return false;
  await registerGrantedToken();
  return true;
}

export async function unregisterPushTokenForLogout() {
  const installationId = await SecureStore.getItemAsync(INSTALLATION_KEY);
  const token = await SecureStore.getItemAsync(TOKEN_KEY);
  if (!installationId && !token) return;
  try {
    await disableDevicePushToken({ installation_id: installationId ?? undefined, token: token ?? undefined });
  } finally {
    await SecureStore.deleteItemAsync(TOKEN_KEY);
  }
}
