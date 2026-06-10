import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import {
  getGradeThresholds, setGradeThresholds, resetGradeThresholds, scoreToGradeLabel,
} from './gradeThresholds.js';

beforeEach(() => resetGradeThresholds());

test('defaults match backend Q2 thresholds', () => {
  assert.deepEqual(getGradeThresholds(), [
    [9, 'Exemplary'], [7, 'Good'], [5, 'Adequate'], [3, 'Poor'],
  ]);
});

test('scoreToGradeLabel maps with defaults', () => {
  assert.equal(scoreToGradeLabel(9.2), 'Exemplary');
  assert.equal(scoreToGradeLabel(7.0), 'Good');
  assert.equal(scoreToGradeLabel(5.1), 'Adequate');
  assert.equal(scoreToGradeLabel(3.0), 'Poor');
  assert.equal(scoreToGradeLabel(2.9), 'Critical');
});

test('scoreToGradeLabel handles strings like "9.1/10" and bad input', () => {
  assert.equal(scoreToGradeLabel('9.1/10'), 'Exemplary');
  assert.equal(scoreToGradeLabel(null), null);
  assert.equal(scoreToGradeLabel('n/a'), null);
});

test('setGradeThresholds changes the mapping', () => {
  setGradeThresholds([[9.5, 'Exemplary'], [8, 'Good'], [6, 'Adequate'], [4, 'Poor']]);
  assert.equal(scoreToGradeLabel(9.2), 'Good');
  assert.equal(scoreToGradeLabel(3.9), 'Critical');
});

test('setGradeThresholds ignores junk', () => {
  setGradeThresholds(undefined);
  setGradeThresholds([]);
  assert.equal(scoreToGradeLabel(9.2), 'Exemplary');
});
