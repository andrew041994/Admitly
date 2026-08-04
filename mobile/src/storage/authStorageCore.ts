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

  async function migrateCredential(secureKey: string, legacyKey: string): Promise<string | null> {
    const secureValue = await secureStorage.getItem(secureKey);
    const legacyValue = await legacyStorage.getItem(legacyKey);

    if (secureValue !== null) {
      if (legacyValue !== null) {
        await legacyStorage.removeItem(legacyKey);
      }
      return secureValue;
    }

    if (legacyValue === null) {
      return null;
    }

    await secureStorage.setItem(secureKey, legacyValue);
    const verifiedValue = await secureStorage.getItem(secureKey);
    if (verifiedValue !== legacyValue) {
      throw new Error(`Secure credential verification failed for ${secureKey}`);
    }

    await legacyStorage.removeItem(legacyKey);
    return verifiedValue;
  }

  async function migrateLegacyCredentials(): Promise<StoredSession | null> {
    try {
      const accessToken = await migrateCredential(keys.secureAccessToken, keys.legacyAccessToken);
      const refreshToken = await migrateCredential(keys.secureRefreshToken, keys.legacyRefreshToken);

      if (!accessToken) {
        if (refreshToken) {
          await clearAllCredentials();
        }
        return null;
      }

      return { accessToken, refreshToken };
    } catch {
      await clearAllCredentials();
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
      await clearAllCredentials();
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
      await clearAllCredentials();
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
