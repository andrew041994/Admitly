export type StoredSession = {
  accessToken: string;
  refreshToken: string | null;
};

type StorageAdapter = {
  getItem: (key: string) => Promise<string | null>;
  setItem: (key: string, value: string) => Promise<void>;
  removeItem: (key: string) => Promise<void>;
};

type LegacyStorageAdapter = Pick<StorageAdapter, 'getItem' | 'removeItem'>;

type AuthStorageKeys = {
  secureAccessToken: string;
  secureRefreshToken: string;
  legacyAccessToken: string;
  legacyRefreshToken: string;
};

type AuthStorageDependencies = {
  secureStorage: StorageAdapter;
  legacyStorage: LegacyStorageAdapter;
  keys: AuthStorageKeys;
};

export function createAuthStorage({ secureStorage, legacyStorage, keys }: AuthStorageDependencies) {
  async function clearAllCredentials(): Promise<void> {
    await Promise.allSettled([
      secureStorage.removeItem(keys.secureAccessToken),
      secureStorage.removeItem(keys.secureRefreshToken),
      legacyStorage.removeItem(keys.legacyAccessToken),
      legacyStorage.removeItem(keys.legacyRefreshToken),
    ]);
  }

  async function restoreSecureCredential(key: string, previousValue: string | null): Promise<void> {
    if (previousValue === null) {
      await secureStorage.removeItem(key);
    } else {
      await secureStorage.setItem(key, previousValue);
    }
  }

  async function migrateLegacyCredentials(): Promise<StoredSession | null> {
    const previousAccessToken = await secureStorage.getItem(keys.secureAccessToken);
    const previousRefreshToken = await secureStorage.getItem(keys.secureRefreshToken);

    if (previousAccessToken !== null && previousRefreshToken !== null) {
      await Promise.all([
        legacyStorage.removeItem(keys.legacyAccessToken),
        legacyStorage.removeItem(keys.legacyRefreshToken),
      ]);
      return { accessToken: previousAccessToken, refreshToken: previousRefreshToken };
    }

    const legacyAccessToken = previousAccessToken === null
      ? await legacyStorage.getItem(keys.legacyAccessToken)
      : null;
    const legacyRefreshToken = previousRefreshToken === null
      ? await legacyStorage.getItem(keys.legacyRefreshToken)
      : null;
    const accessToken = previousAccessToken ?? legacyAccessToken;
    const refreshToken = previousRefreshToken ?? legacyRefreshToken;

    if (!accessToken) {
      return null;
    }

    try {
      if (previousAccessToken === null) {
        await secureStorage.setItem(keys.secureAccessToken, accessToken);
      }
      if (previousRefreshToken === null && refreshToken !== null) {
        await secureStorage.setItem(keys.secureRefreshToken, refreshToken);
      }

      const [verifiedAccessToken, verifiedRefreshToken] = await Promise.all([
        secureStorage.getItem(keys.secureAccessToken),
        secureStorage.getItem(keys.secureRefreshToken),
      ]);
      if (verifiedAccessToken !== accessToken || verifiedRefreshToken !== refreshToken) {
        throw new Error('Secure credential migration verification failed');
      }

      await Promise.all([
        legacyStorage.removeItem(keys.legacyAccessToken),
        legacyStorage.removeItem(keys.legacyRefreshToken),
      ]);
      return { accessToken, refreshToken };
    } catch {
      await Promise.allSettled([
        restoreSecureCredential(keys.secureAccessToken, previousAccessToken),
        restoreSecureCredential(keys.secureRefreshToken, previousRefreshToken),
      ]);
      return null;
    }
  }

  async function getAccessToken(): Promise<string | null> {
    const session = await migrateLegacyCredentials();
    return session?.accessToken ?? null;
  }

  async function getRefreshToken(): Promise<string | null> {
    const session = await migrateLegacyCredentials();
    return session?.refreshToken ?? null;
  }

  async function getStoredSession(): Promise<StoredSession | null> {
    return migrateLegacyCredentials();
  }

  async function writeCredential(secureKey: string, legacyKey: string, value: string | null): Promise<void> {
    const previousValue = await secureStorage.getItem(secureKey);
    try {
      if (value === null) {
        await secureStorage.removeItem(secureKey);
      } else {
        await secureStorage.setItem(secureKey, value);
        const verifiedValue = await secureStorage.getItem(secureKey);
        if (verifiedValue !== value) {
          throw new Error(`Secure credential verification failed for ${secureKey}`);
        }
      }
      await legacyStorage.removeItem(legacyKey);
    } catch (error) {
      await Promise.allSettled([restoreSecureCredential(secureKey, previousValue)]);
      throw error;
    }
  }

  async function setAccessToken(accessToken: string): Promise<void> {
    await writeCredential(keys.secureAccessToken, keys.legacyAccessToken, accessToken);
  }

  async function setRefreshToken(refreshToken: string | null): Promise<void> {
    await writeCredential(keys.secureRefreshToken, keys.legacyRefreshToken, refreshToken);
  }

  async function setStoredSession(session: StoredSession): Promise<void> {
    const [previousAccessToken, previousRefreshToken] = await Promise.all([
      secureStorage.getItem(keys.secureAccessToken),
      secureStorage.getItem(keys.secureRefreshToken),
    ]);
    try {
      await secureStorage.setItem(keys.secureAccessToken, session.accessToken);
      if (session.refreshToken) {
        await secureStorage.setItem(keys.secureRefreshToken, session.refreshToken);
      } else {
        await secureStorage.removeItem(keys.secureRefreshToken);
      }

      const [verifiedAccessToken, verifiedRefreshToken] = await Promise.all([
        secureStorage.getItem(keys.secureAccessToken),
        secureStorage.getItem(keys.secureRefreshToken),
      ]);
      if (verifiedAccessToken !== session.accessToken || verifiedRefreshToken !== session.refreshToken) {
        throw new Error('Secure credential verification failed');
      }

      await Promise.all([
        legacyStorage.removeItem(keys.legacyAccessToken),
        legacyStorage.removeItem(keys.legacyRefreshToken),
      ]);
    } catch (error) {
      await Promise.allSettled([
        restoreSecureCredential(keys.secureAccessToken, previousAccessToken),
        restoreSecureCredential(keys.secureRefreshToken, previousRefreshToken),
      ]);
      throw error;
    }
  }

  return {
    getAccessToken,
    setAccessToken,
    getRefreshToken,
    setRefreshToken,
    getStoredSession,
    setStoredSession,
    clearStoredSession: clearAllCredentials,
    migrateLegacyCredentials,
  };
}
