const assert = require('node:assert/strict');
const Module = require('node:module');
const path = require('node:path');
const test = require('node:test');
const { transformFileSync } = require('@babel/core');

const filename = path.join(__dirname, 'emailValidation.ts');
const result = transformFileSync(filename, {
  babelrc: false,
  configFile: false,
  plugins: ['@babel/plugin-transform-typescript', '@babel/plugin-transform-modules-commonjs'],
});
const loaded = new Module(filename, module);
loaded.filename = filename;
loaded.paths = Module._nodeModulePaths(__dirname);
loaded._compile(result.code, filename);
const { normalizeEmailAddress } = loaded.exports;

test('authentication email validation trims and lowercases valid modern addresses', () => {
  assert.equal(normalizeEmailAddress(' First.Last+Tickets@Example.MUSEUM '), 'first.last+tickets@example.museum');
  assert.equal(normalizeEmailAddress("customer's-tag@example.co.gy"), "customer's-tag@example.co.gy");
});

test('authentication email validation rejects clearly malformed addresses', () => {
  for (const email of ['missing-at.example.com', '@example.com', 'person@', 'person@localhost', 'two@@example.com', 'a b@example.com', '.start@example.com', 'end.@example.com', 'a..b@example.com']) {
    assert.equal(normalizeEmailAddress(email), null, email);
  }
});
