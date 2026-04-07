import AsyncStorage from '@react-native-async-storage/async-storage';

import { storageKeys } from './keys';

export async function getStoredSessionToken(): Promise<string | null> {
  return AsyncStorage.getItem(storageKeys.sessionToken);
}

export async function setStoredSessionToken(token: string): Promise<void> {
  await AsyncStorage.setItem(storageKeys.sessionToken, token);
}

export async function clearStoredSessionToken(): Promise<void> {
  await AsyncStorage.removeItem(storageKeys.sessionToken);
}
