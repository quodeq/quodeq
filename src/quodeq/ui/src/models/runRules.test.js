import test from 'node:test';
import assert from 'node:assert/strict';

import {
  LOW_CONFIDENCE_THRESHOLD,
  SCORE_THRESHOLDS,
  isFrozenRun,
  isLowConfidence,
  scoreTier,
} from './runRules.js';

test('isFrozenRun: a completed historical run is frozen', () => {
  const runs = [{ runId: 'r1', status: 'complete' }];
  assert.equal(isFrozenRun('r1', runs), true);
});

test('isFrozenRun: an in-progress run is never frozen', () => {
  const runs = [{ runId: 'r1', status: 'in_progress' }];
  assert.equal(isFrozenRun('r1', runs), false);
});

test('isFrozenRun: "latest" is never frozen — it tracks a moving target', () => {
  assert.equal(isFrozenRun('latest', [{ runId: 'latest', status: 'complete' }]), false);
});

test('isFrozenRun: no selection is not frozen', () => {
  assert.equal(isFrozenRun(null, []), false);
  assert.equal(isFrozenRun('', []), false);
});

test('isFrozenRun: an unknown run counts as frozen', () => {
  // By the time a run detail opens, the runs list is cached; treating the
  // brief unknown window as frozen avoids a spurious mount refetch.
  assert.equal(isFrozenRun('r-missing', [{ runId: 'r1', status: 'complete' }]), true);
  assert.equal(isFrozenRun('r1', null), true);
});

test('isLowConfidence: below the threshold only, and only for numbers', () => {
  assert.equal(isLowConfidence({ confidence: LOW_CONFIDENCE_THRESHOLD - 1 }), true);
  assert.equal(isLowConfidence({ confidence: LOW_CONFIDENCE_THRESHOLD }), false);
  assert.equal(isLowConfidence({ confidence: 100 }), false);
  assert.equal(isLowConfidence({}), false);
  assert.equal(isLowConfidence(null), false);
  assert.equal(isLowConfidence({ confidence: 'low' }), false);
});

test('scoreTier: maps a score onto the backend grading tiers', () => {
  assert.equal(scoreTier(9.5), 'exemplary');
  assert.equal(scoreTier(SCORE_THRESHOLDS.exemplary), 'exemplary');
  assert.equal(scoreTier(8), 'good');
  assert.equal(scoreTier(6), 'adequate');
  assert.equal(scoreTier(4), 'poor');
  assert.equal(scoreTier(1), 'unacceptable');
});

test('scoreTier: a missing or non-numeric score has no tier', () => {
  assert.equal(scoreTier(null), null);
  assert.equal(scoreTier(undefined), null);
  assert.equal(scoreTier('7'), null);
});
