import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readAnalysisPower, DEFAULT_ANALYSIS_POWER } from './evaluationLifecycleHelpers.js';

function storageWith(value) {
  return { getItem: () => value };
}

function throwingStorage() {
  return { getItem: () => { throw new Error('storage unavailable'); } };
}

test('readAnalysisPower: returns the stored tier when it is a valid integer in range', () => {
  assert.equal(readAnalysisPower(storageWith('1')), 1);
  assert.equal(readAnalysisPower(storageWith('3')), 3);
});

test('readAnalysisPower: falls back to the default when nothing is stored', () => {
  assert.equal(readAnalysisPower(storageWith(null)), DEFAULT_ANALYSIS_POWER);
});

test('readAnalysisPower: falls back to the default when the stored value is out of range', () => {
  assert.equal(readAnalysisPower(storageWith('0')), DEFAULT_ANALYSIS_POWER);
  assert.equal(readAnalysisPower(storageWith('4')), DEFAULT_ANALYSIS_POWER);
  assert.equal(readAnalysisPower(storageWith('-1')), DEFAULT_ANALYSIS_POWER);
});

test('readAnalysisPower: falls back to the default when the stored value is not a number at all', () => {
  assert.equal(readAnalysisPower(storageWith('not-a-number')), DEFAULT_ANALYSIS_POWER);
});

test('readAnalysisPower: falls back to the default when the stored value is a non-integer number', () => {
  // Number('1.5') is a real number but not a valid tier index.
  assert.equal(readAnalysisPower(storageWith('1.5')), DEFAULT_ANALYSIS_POWER);
});

test('readAnalysisPower: falls back to the default when the store throws', () => {
  assert.equal(readAnalysisPower(throwingStorage()), DEFAULT_ANALYSIS_POWER);
});
