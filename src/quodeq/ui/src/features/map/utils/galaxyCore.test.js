import test from 'node:test';
import assert from 'node:assert/strict';
import { scoreRGB, sevRGB } from '../viz/core/galaxyCore.js';

// galaxyCore.js requires a DOM (document.createElement, getComputedStyle,
// MutationObserver) for its default theme-reading path, so every case here
// passes explicit colors/thresholds — the lazy-default options-object params
// that let scoreRGB/sevRGB skip the DOM entirely when a caller supplies them.

const COLORS = {
  gradeTop: { r: 1, g: 1, b: 1 },
  gradeHigh: { r: 2, g: 2, b: 2 },
  gradeMid: { r: 3, g: 3, b: 3 },
  gradeLow: { r: 4, g: 4, b: 4 },
  gradeBottom: { r: 5, g: 5, b: 5 },
  critical: { r: 9, g: 0, b: 0 },
  major: { r: 8, g: 0, b: 0 },
  minor: { r: 7, g: 0, b: 0 },
};

// Mirrors DEFAULT_THRESHOLDS in utils/gradeThresholds.js.
const THRESHOLDS = [[9, 'Exemplary'], [7, 'Good'], [5, 'Adequate'], [3, 'Poor']];

test('scoreRGB: picks the tier color matching the injected thresholds', () => {
  assert.deepEqual(scoreRGB(9.5, { colors: COLORS, thresholds: THRESHOLDS }), COLORS.gradeTop);
  assert.deepEqual(scoreRGB(7.2, { colors: COLORS, thresholds: THRESHOLDS }), COLORS.gradeHigh);
  assert.deepEqual(scoreRGB(5.0, { colors: COLORS, thresholds: THRESHOLDS }), COLORS.gradeMid);
  assert.deepEqual(scoreRGB(3.1, { colors: COLORS, thresholds: THRESHOLDS }), COLORS.gradeLow);
});

test('scoreRGB: below every threshold falls back to gradeBottom', () => {
  assert.deepEqual(scoreRGB(0, { colors: COLORS, thresholds: THRESHOLDS }), COLORS.gradeBottom);
  assert.deepEqual(scoreRGB(2.9, { colors: COLORS, thresholds: THRESHOLDS }), COLORS.gradeBottom);
});

test('scoreRGB: respects injected thresholds independent of the live grade table', () => {
  // A custom two-tier table: only gradeTop/gradeLow are reachable.
  const customThresholds = [[8, 'High'], [0, 'Low']];
  assert.deepEqual(scoreRGB(8, { colors: COLORS, thresholds: customThresholds }), COLORS.gradeTop);
  assert.deepEqual(scoreRGB(4, { colors: COLORS, thresholds: customThresholds }), COLORS.gradeHigh);
});

test('sevRGB: maps a known severity to its color', () => {
  assert.deepEqual(sevRGB('critical', { colors: COLORS }), COLORS.critical);
  assert.deepEqual(sevRGB('major', { colors: COLORS }), COLORS.major);
  assert.deepEqual(sevRGB('minor', { colors: COLORS }), COLORS.minor);
});

test('sevRGB: unknown severity falls back to minor', () => {
  assert.deepEqual(sevRGB('unknown', { colors: COLORS }), COLORS.minor);
  assert.deepEqual(sevRGB(undefined, { colors: COLORS }), COLORS.minor);
});
