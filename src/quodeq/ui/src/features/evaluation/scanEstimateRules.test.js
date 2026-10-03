import { test } from 'node:test';
import assert from 'node:assert/strict';
import { queuedFileAnalyses } from './scanEstimateRules.js';

test('null when there are no estimates', () => {
  assert.equal(queuedFileAnalyses(new Set(['security']), null, false), null);
  assert.equal(queuedFileAnalyses(new Set(['security']), {}, false), null);
});

test('null when every picked dimension is missing from the estimates', () => {
  const estimates = { dimensions: { reliability: { total: 10, count: 2 } } };
  assert.equal(queuedFileAnalyses(new Set(['security']), estimates, false), null);
});

test('sums count (incremental) across picked dimensions', () => {
  const estimates = { dimensions: { security: { total: 10, count: 2 }, reliability: { total: 20, count: 3 } } };
  assert.equal(queuedFileAnalyses(new Set(['security', 'reliability']), estimates, false), 5);
});

test('sums total (clean scan) across picked dimensions', () => {
  const estimates = { dimensions: { security: { total: 10, count: 2 }, reliability: { total: 20, count: 3 } } };
  assert.equal(queuedFileAnalyses(new Set(['security', 'reliability']), estimates, true), 30);
});

test('a picked dimension missing an estimate is skipped, not treated as 0-and-counted', () => {
  const estimates = { dimensions: { security: { total: 10, count: 2 } } };
  assert.equal(queuedFileAnalyses(new Set(['security', 'reliability']), estimates, true), 10);
});
