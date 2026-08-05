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
const { ACTIVE_TRANSFER_METHODS, PHONE_TRANSFER_LABEL, canCreateResolvedTransfer, canSubmitTransfer, isPendingTransfer, maskTransferIdentifier, normalizePhoneNumber, normalizeTransferIdentifier } = loaded.exports;

test('phone validation normalizes Guyana local and international formats', () => {
  assert.equal(normalizePhoneNumber('600 1234'), '+5926001234');
  assert.equal(normalizePhoneNumber('011 592 600 1234'), null);
  assert.equal(normalizePhoneNumber('00 592 600 1234'), '+5926001234');
  assert.equal(normalizePhoneNumber('+1 (555) 000-1111'), '+15550001111');
  assert.equal(normalizePhoneNumber('12345'), null);
});

test('transfer form validates email while retaining phone normalization for future verification', () => {
  assert.equal(normalizeTransferIdentifier('email', ' Person@Example.COM '), 'person@example.com');
  assert.equal(normalizeTransferIdentifier('email', 'not-an-email'), null);
  assert.equal(normalizeTransferIdentifier('phone', '600-1234'), '+5926001234');
});

test('email is the only active transfer method and phone is clearly unavailable', () => {
  assert.deepEqual(ACTIVE_TRANSFER_METHODS, ['email']);
  assert.equal(PHONE_TRANSFER_LABEL, 'Phone transfer — coming after phone verification');
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
