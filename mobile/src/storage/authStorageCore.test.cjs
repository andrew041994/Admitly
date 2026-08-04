const assert = require('node:assert/strict');
const Module = require('node:module');
const path = require('node:path');
const test = require('node:test');

const { transformFileSync } = require('@babel/core');

function loadAuthStorageCore() {
  const filename = path.join(__dirname, 'authStorageCore.ts');
  const result = transformFileSync(filename, {
    babelrc: false,
    configFile: false,
    plugins: ['@babel/plugin-transform-typescript', '@babel/plugin-transform-modules-commonjs'],
  });
  const loadedModule = new Module(filename, module);
  loadedModule.filename = filename;
  loadedModule.paths = Module._nodeModulePaths(__dirname);
  loadedModule._compile(result.code, filename);
  return loadedModule.exports;
}

const { createAuthStorage } = loadAuthStorageCore();

const keys = {
  secureAccessToken: 'secure.access',
  secureRefreshToken: 'secure.refresh',
  legacyAccessToken: 'legacy.access',
  legacyRefreshToken: 'legacy.refresh',
};

function createMemoryStorage(initialValues = {}, options = {}) {
  const values = new Map(Object.entries(initialValues));
  const writes = [];

  return {
    values,
    writes,
    adapter: {
      async getItem(key) {
        return values.get(key) ?? null;
      },
      async setItem(key, value) {
        if (options.failSetKey === key) {
          throw new Error('set failed');
        }
        writes.push([key, value]);
        values.set(key, value);
      },
      async removeItem(key) {
        values.delete(key);
      },
    },
  };
}

function setup(secureInitial = {}, legacyInitial = {}, secureOptions = {}) {
  const secure = createMemoryStorage(secureInitial, secureOptions);
  const legacy = createMemoryStorage(legacyInitial);
  const storage = createAuthStorage({ secureStorage: secure.adapter, legacyStorage: legacy.adapter, keys });
  return { storage, secure, legacy };
}

test('fresh credential saves write tokens only to secure storage', async () => {
  const { storage, secure, legacy } = setup({}, {
    [keys.legacyAccessToken]: 'stale-access',
    [keys.legacyRefreshToken]: 'stale-refresh',
  });

  await storage.setStoredSession({ accessToken: 'new-access', refreshToken: 'new-refresh' });

  assert.equal(secure.values.get(keys.secureAccessToken), 'new-access');
  assert.equal(secure.values.get(keys.secureRefreshToken), 'new-refresh');
  assert.equal(legacy.values.size, 0);
});

test('legacy credentials migrate, verify, and are removed idempotently', async () => {
  const { storage, secure, legacy } = setup({}, {
    [keys.legacyAccessToken]: 'legacy-access',
    [keys.legacyRefreshToken]: 'legacy-refresh',
  });

  const first = await storage.migrateLegacyCredentials();
  const second = await storage.migrateLegacyCredentials();

  assert.deepEqual(first, { accessToken: 'legacy-access', refreshToken: 'legacy-refresh' });
  assert.deepEqual(second, first);
  assert.equal(secure.values.get(keys.secureAccessToken), 'legacy-access');
  assert.equal(secure.values.get(keys.secureRefreshToken), 'legacy-refresh');
  assert.equal(legacy.values.size, 0);
});

test('existing secure credentials win and duplicate legacy values are removed', async () => {
  const { storage, secure, legacy } = setup({
    [keys.secureAccessToken]: 'secure-access',
    [keys.secureRefreshToken]: 'secure-refresh',
  }, {
    [keys.legacyAccessToken]: 'legacy-access',
    [keys.legacyRefreshToken]: 'legacy-refresh',
  });

  assert.deepEqual(await storage.getStoredSession(), {
    accessToken: 'secure-access',
    refreshToken: 'secure-refresh',
  });
  assert.equal(secure.values.get(keys.secureAccessToken), 'secure-access');
  assert.equal(secure.values.get(keys.secureRefreshToken), 'secure-refresh');
  assert.equal(legacy.values.size, 0);
});

test('failed migration clears partial secure and legacy credentials', async () => {
  const { storage, secure, legacy } = setup({}, {
    [keys.legacyAccessToken]: 'legacy-access',
    [keys.legacyRefreshToken]: 'legacy-refresh',
  }, { failSetKey: keys.secureRefreshToken });

  assert.equal(await storage.migrateLegacyCredentials(), null);
  assert.equal(secure.values.size, 0);
  assert.equal(legacy.values.size, 0);
});

test('session restoration reads credentials from secure storage', async () => {
  const { storage, secure } = setup({
    [keys.secureAccessToken]: 'secure-access',
    [keys.secureRefreshToken]: 'secure-refresh',
  });

  assert.deepEqual(await storage.getStoredSession(), {
    accessToken: 'secure-access',
    refreshToken: 'secure-refresh',
  });
  assert.equal(secure.writes.length, 0);
});

test('clearing a session removes secure and legacy credentials', async () => {
  const { storage, secure, legacy } = setup({
    [keys.secureAccessToken]: 'secure-access',
    [keys.secureRefreshToken]: 'secure-refresh',
  }, {
    [keys.legacyAccessToken]: 'legacy-access',
    [keys.legacyRefreshToken]: 'legacy-refresh',
  });

  await storage.clearStoredSession();
  await storage.clearStoredSession();

  assert.equal(secure.values.size, 0);
  assert.equal(legacy.values.size, 0);
});
