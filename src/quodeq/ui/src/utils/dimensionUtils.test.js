import test from 'node:test';
import assert from 'node:assert/strict';
import { fallbackDelta } from './dimensionUtils.js';

test('fallbackDelta: returns the numeric difference when both scores are present', () => {
  assert.equal(fallbackDelta({ overallScore: 8.5, previousScore: 7 }), 1.5);
  assert.equal(fallbackDelta({ overallScore: '6', previousScore: '9' }), -3);
});

test('fallbackDelta: null when either score is missing or non-numeric', () => {
  assert.equal(fallbackDelta({ overallScore: 8, previousScore: undefined }), null);
  assert.equal(fallbackDelta({ overallScore: undefined, previousScore: 8 }), null);
  assert.equal(fallbackDelta({ overallScore: 'n/a', previousScore: 7 }), null);
  assert.equal(fallbackDelta({}), null);
});
