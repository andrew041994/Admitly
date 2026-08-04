import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';

import { createAuthStorage, StoredSession } from './authStorageCore';
import { legacyStorageKeys, secureStorageKeys } from './keys';

const authStorage = createAuthStorage({
  secureStorage: {
    getItem: SecureStore.getItemAsync,
    setItem: SecureStore.setItemAsync,
    removeItem: SecureStore.deleteItemAsync,
  },
  legacyStorage: {
    getItem: AsyncStorage.getItem,
    removeItem: AsyncStorage.removeItem,
  },
  keys: {
    secureAccessToken: secureStorageKeys.accessToken,
    secureRefreshToken: secureStorageKeys.refreshToken,
    legacyAccessToken: legacyStorageKeys.sessionToken,
    legacyRefreshToken: legacyStorageKeys.refreshToken,
  },
});

export type { StoredSession };
export const getAccessToken = authStorage.getAccessToken;
export const setAccessToken = authStorage.setAccessToken;
export const getRefreshToken = authStorage.getRefreshToken;
export const setRefreshToken = authStorage.setRefreshToken;
export const getStoredSession = authStorage.getStoredSession;
export const setStoredSession = authStorage.setStoredSession;
export const clearStoredSession = authStorage.clearStoredSession;
export const migrateLegacyCredentials = authStorage.migrateLegacyCredentials;
