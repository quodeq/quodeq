import test from 'node:test';
import assert from 'node:assert/strict';
import { formatScore } from './shared.js';

test('formatScore: renders an average out of ten, rounded to one decimal', () => {
  assert.equal(formatScore(7.84), '7.8/10');
  assert.equal(formatScore(8), '8/10');
  assert.equal(formatScore(7.75), '7.8/10');
  assert.equal(formatScore(0), '0/10');
});

test('formatScore: accepts the numeric string the run summary carries', () => {
  assert.equal(formatScore('7.84'), '7.8/10');
  assert.equal(formatScore('8'), '8/10');
});

test('formatScore: an absent score is an em dash', () => {
  assert.equal(formatScore(null), '—');
  assert.equal(formatScore(undefined), '—');
});
