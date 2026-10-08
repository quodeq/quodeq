import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildDimMetas, buildUpToDateIds } from './dimMetas.js';

// A dimension card says only what the run will do with it. "N% analyzed"
// beside "4 files to analyze" rounded 3,888 of 3,892 up to 100%.
test('a card says what the run will do, nothing more', () => {
  const metas = buildDimMetas({ dimensions: { ca: { count: 4, total: 3892, cached: 3888 }, sec: { count: 0, total: 3892, cached: 3892 } } }, false);
  assert.deepEqual(metas.ca, ['4 files to analyze']);
  assert.deepEqual(metas.sec, ['up to date']);
});

test('a clean scan analyzes every file of a dimension', () => {
  const metas = buildDimMetas({ dimensions: { sec: { count: 0, total: 3892, cached: 3892 } } }, true);
  assert.deepEqual(metas.sec, ['3,892 files to analyze']);
});

test('up to date means nothing to analyze, and never in clean scan', () => {
  const est = { dimensions: { ca: { count: 4, total: 3892 }, sec: { count: 0, total: 3892 }, none: { count: 0, total: 0 } } };
  assert.deepEqual([...buildUpToDateIds(est, false)], ['sec']);
  assert.equal(buildUpToDateIds(est, true).size, 0);
  assert.equal(buildUpToDateIds(null, false).size, 0);
});
