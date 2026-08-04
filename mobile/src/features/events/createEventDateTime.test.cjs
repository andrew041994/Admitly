const assert = require('node:assert/strict');
const Module = require('node:module');
const path = require('node:path');
const test = require('node:test');

const { transformFileSync } = require('@babel/core');

function loadDateTimeHelpers() {
  const filename = path.join(__dirname, 'createEventDateTime.ts');
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

const {
  applyDateSelection,
  applyTimeSelection,
  combineLocalDateAndTime,
  getConfirmedPickerValue,
  isEndAfterStart,
} = loadDateTimeHelpers();

function localDate(year, month, day, hour = 0, minute = 0) {
  return new Date(year, month - 1, day, hour, minute, 0, 0);
}

test('confirming a start date updates it once and preserves the start time', () => {
  const time = localDate(2026, 1, 1, 19, 45);
  const result = applyDateSelection({ date: localDate(2026, 8, 1), time }, localDate(2026, 9, 12));

  assert.equal(result.date.getFullYear(), 2026);
  assert.equal(result.date.getMonth(), 8);
  assert.equal(result.date.getDate(), 12);
  assert.equal(result.time, time);
});

test('confirming a start time updates it once and preserves the start date', () => {
  const date = localDate(2026, 9, 12);
  const result = applyTimeSelection({ date, time: localDate(2026, 1, 1, 18, 0) }, localDate(2026, 1, 1, 20, 30));

  assert.equal(result.date, date);
  assert.equal(result.time.getHours(), 20);
  assert.equal(result.time.getMinutes(), 30);
});

test('confirming an end date updates it once and preserves the end time', () => {
  const time = localDate(2026, 1, 1, 23, 15);
  const result = applyDateSelection({ date: localDate(2026, 9, 12), time }, localDate(2026, 9, 13));

  assert.equal(result.date.getDate(), 13);
  assert.equal(result.time, time);
});

test('confirming an end time updates it once and preserves the end date', () => {
  const date = localDate(2026, 9, 13);
  const result = applyTimeSelection({ date, time: localDate(2026, 1, 1, 22, 0) }, localDate(2026, 1, 1, 23, 30));

  assert.equal(result.date, date);
  assert.equal(result.time.getHours(), 23);
  assert.equal(result.time.getMinutes(), 30);
});

test('dismissed and neutral picker events never produce a value', () => {
  const value = localDate(2026, 9, 12, 19, 45);

  assert.equal(getConfirmedPickerValue('dismissed', value), null);
  assert.equal(getConfirmedPickerValue('neutralButtonPressed', value), null);
  assert.equal(getConfirmedPickerValue('set', undefined), null);
  assert.equal(getConfirmedPickerValue('set', value), value);
});

test('local date and time components combine without a UTC shift', () => {
  const combined = combineLocalDateAndTime({
    date: localDate(2026, 9, 12),
    time: localDate(2026, 1, 1, 19, 45),
  });

  assert.equal(combined.getFullYear(), 2026);
  assert.equal(combined.getMonth(), 8);
  assert.equal(combined.getDate(), 12);
  assert.equal(combined.getHours(), 19);
  assert.equal(combined.getMinutes(), 45);
});

test('end-time validation accepts only an end strictly after the start', () => {
  const start = { date: localDate(2026, 9, 12), time: localDate(2026, 1, 1, 19, 45) };
  const later = { date: localDate(2026, 9, 12), time: localDate(2026, 1, 1, 20, 0) };
  const equal = { date: localDate(2026, 9, 12), time: localDate(2026, 1, 1, 19, 45) };
  const earlier = { date: localDate(2026, 9, 11), time: localDate(2026, 1, 1, 23, 0) };

  assert.equal(isEndAfterStart(start, later), true);
  assert.equal(isEndAfterStart(start, equal), false);
  assert.equal(isEndAfterStart(start, earlier), false);
});
