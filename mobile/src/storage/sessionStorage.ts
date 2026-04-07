import AsyncStorage from '@react-native-async-storage/async-storage';

import { storageKeys } from './keys';

export type StoredSession = {
  accessToken: string;
  refreshToken: string | null;
};

export async function getStoredSession(): Promise<StoredSession | null> {
  const [accessToken, refreshToken] = await Promise.all([
    AsyncStorage.getItem(storageKeys.sessionToken),
    AsyncStorage.getItem(storageKeys.refreshToken),
  ]);

  if (!accessToken) {
    return null;
  }

  return {
    accessToken,
    refreshToken,
  };
}

export async function setStoredSession(session: StoredSession): Promise<void> {
  const writes: Array<Promise<void>> = [AsyncStorage.setItem(storageKeys.sessionToken, session.accessToken)];

  if (session.refreshToken) {
    writes.push(AsyncStorage.setItem(storageKeys.refreshToken, session.refreshToken));
  } else {
    writes.push(AsyncStorage.removeItem(storageKeys.refreshToken));
  }

  await Promise.all(writes);
}

export async function clearStoredSession(): Promise<void> {
  await Promise.all([
    AsyncStorage.removeItem(storageKeys.sessionToken),
    AsyncStorage.removeItem(storageKeys.refreshToken),
  ]);
}
