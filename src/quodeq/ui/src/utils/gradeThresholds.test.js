import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import {
  getGradeThresholds, setGradeThresholds, resetGradeThresholds, scoreToGradeLabel,
  createGradeThresholdsStore, defaultGradeThresholdsStore,
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

test('getGradeThresholds returns a frozen table that callers cannot mutate', () => {
  const t = getGradeThresholds();
  assert.ok(Object.isFrozen(t));
  assert.ok(Object.isFrozen(t[0]));
  assert.throws(() => { t.push([1, 'x']); }, TypeError);
  assert.throws(() => { t[0][0] = 0; }, TypeError);
  // The shared table is unchanged after the failed mutations.
  assert.equal(scoreToGradeLabel(9.2), 'Exemplary');
});

test('setGradeThresholds result is also frozen', () => {
  setGradeThresholds([[9.5, 'Exemplary'], [8, 'Good'], [6, 'Adequate'], [4, 'Poor']]);
  const t = getGradeThresholds();
  assert.ok(Object.isFrozen(t));
  assert.ok(Object.isFrozen(t[0]));
});

test('setGradeThresholds ignores junk', () => {
  setGradeThresholds(undefined);
  setGradeThresholds([]);
  assert.equal(scoreToGradeLabel(9.2), 'Exemplary');
});

// ── store isolation (createGradeThresholdsStore) ───────────────────────

test('two store instances do not share state', () => {
  const a = createGradeThresholdsStore();
  const b = createGradeThresholdsStore();
  a.set([[9.5, 'Exemplary'], [8, 'Good'], [6, 'Adequate'], [4, 'Poor']]);
  assert.equal(a.scoreToGradeLabel(9.2), 'Good');
  // b (and the module default) still grade with the defaults.
  assert.equal(b.scoreToGradeLabel(9.2), 'Exemplary');
  assert.equal(scoreToGradeLabel(9.2), 'Exemplary');
});

test('an isolated store supports the full get/set/reset/label surface', () => {
  const s = createGradeThresholdsStore();
  assert.deepEqual(s.get(), [[9, 'Exemplary'], [7, 'Good'], [5, 'Adequate'], [3, 'Poor']]);
  s.set([[6, 'Good'], [2, 'Poor']]);
  assert.equal(s.scoreToGradeLabel(6.5), 'Good');
  assert.equal(s.scoreToGradeLabel(1), 'Critical');
  assert.ok(Object.isFrozen(s.get()));
  s.reset();
  assert.equal(s.scoreToGradeLabel(9.2), 'Exemplary');
});

test('the named exports delegate to the default store instance', () => {
  defaultGradeThresholdsStore.set([[9.5, 'Exemplary'], [8, 'Good'], [6, 'Adequate'], [4, 'Poor']]);
  assert.equal(scoreToGradeLabel(9.2), 'Good');
  assert.deepEqual(getGradeThresholds(), defaultGradeThresholdsStore.get());
  resetGradeThresholds();
  assert.equal(defaultGradeThresholdsStore.scoreToGradeLabel(9.2), 'Exemplary');
});
