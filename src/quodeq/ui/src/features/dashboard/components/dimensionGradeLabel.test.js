import test from 'node:test';
import assert from 'node:assert/strict';
import { dimensionGradeLabel } from './dimensionGradeLabel.js';

test('returns EXEMPLARY for scores >= 9', () => {
  assert.equal(dimensionGradeLabel(9.0), 'EXEMPLARY');
  assert.equal(dimensionGradeLabel(9.7), 'EXEMPLARY');
  assert.equal(dimensionGradeLabel(10), 'EXEMPLARY');
});

test('returns GOOD for 8 <= score < 9', () => {
  assert.equal(dimensionGradeLabel(8.0), 'GOOD');
  assert.equal(dimensionGradeLabel(8.9), 'GOOD');
});

test('returns FAIR for 7 <= score < 8', () => {
  assert.equal(dimensionGradeLabel(7.0), 'FAIR');
  assert.equal(dimensionGradeLabel(7.8), 'FAIR');
});

test('returns POOR for 6 <= score < 7', () => {
  assert.equal(dimensionGradeLabel(6.0), 'POOR');
  assert.equal(dimensionGradeLabel(6.9), 'POOR');
});

test('returns CRITICAL for score < 6', () => {
  assert.equal(dimensionGradeLabel(0), 'CRITICAL');
  assert.equal(dimensionGradeLabel(5.9), 'CRITICAL');
});

test('accepts numeric strings', () => {
  assert.equal(dimensionGradeLabel('9.1'), 'EXEMPLARY');
  assert.equal(dimensionGradeLabel('7.8/10'), 'FAIR');
});

test('returns null for NaN/null/empty input', () => {
  assert.equal(dimensionGradeLabel(null), null);
  assert.equal(dimensionGradeLabel(undefined), null);
  assert.equal(dimensionGradeLabel(NaN), null);
  assert.equal(dimensionGradeLabel(''), null);
  assert.equal(dimensionGradeLabel('not-a-number'), null);
});
