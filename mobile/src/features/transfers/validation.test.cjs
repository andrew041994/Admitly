const assert = require('node:assert/strict');
const Module = require('node:module');
const path = require('node:path');
const test = require('node:test');
const { transformFileSync } = require('@babel/core');

const filename = path.join(__dirname, 'validation.ts');
const result = transformFileSync(filename, {
  babelrc: false,
  configFile: false,
  plugins: ['@babel/plugin-transform-typescript', '@babel/plugin-transform-modules-commonjs'],
});
const loaded = new Module(filename, module);
loaded.filename = filename;
loaded.paths = Module._nodeModulePaths(__dirname);
loaded._compile(result.code, filename);
const { ACTIVE_TRANSFER_METHODS, canCreateResolvedTransfer, canSubmitTransfer, isPendingTransfer, maskTransferIdentifier, normalizeTransferEmail } = loaded.exports;

test('transfer form validates and normalizes email', () => {
  assert.equal(normalizeTransferEmail(' Person@Example.COM '), 'person@example.com');
  assert.equal(normalizeTransferEmail('not-an-email'), null);
});

test('email is the only active transfer method', () => {
  assert.deepEqual(ACTIVE_TRANSFER_METHODS, ['email']);
});

test('recipient identifiers are masked for confirmation and history', () => {
  assert.equal(maskTransferIdentifier('person@example.com'), 'pe****@example.com');
  assert.equal(maskTransferIdentifier('+5926001234'), '+******1234');
});

test('duplicate transfer submissions are blocked while a request is active', () => {
  assert.equal(canSubmitTransfer('person@example.com', false), true);
  assert.equal(canSubmitTransfer('person@example.com', true), false);
  assert.equal(canSubmitTransfer(null, false), false);
  assert.equal(canCreateResolvedTransfer('opaque-reference', false), true);
  assert.equal(canCreateResolvedTransfer('opaque-reference', true), false);
  assert.equal(canCreateResolvedTransfer(null, false), false);
});

test('only pending transfers are shown as actionable inbox or outbox items', () => {
  assert.equal(isPendingTransfer('pending'), true);
  assert.equal(isPendingTransfer('accepted'), false);
  assert.equal(isPendingTransfer('declined'), false);
  assert.equal(isPendingTransfer('canceled'), false);
  assert.equal(isPendingTransfer('expired'), false);
});
