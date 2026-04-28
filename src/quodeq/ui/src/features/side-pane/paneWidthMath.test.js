import { test } from 'node:test';
import assert from 'node:assert/strict';
import { clampSidePaneWidth, MIN_RATIO, MAX_RATIO } from './paneWidthMath.js';

test('clampSidePaneWidth returns the requested width inside the allowed band', () => {
  // 50% of a 1000px viewport = 500
  assert.equal(clampSidePaneWidth(500, 1000), 500);
});

test('clampSidePaneWidth clamps below the minimum (30%)', () => {
  // requested 100px on a 1000px viewport (10%) → 300px (30%)
  assert.equal(clampSidePaneWidth(100, 1000), 300);
});

test('clampSidePaneWidth clamps above the maximum (70%)', () => {
  // requested 900px on a 1000px viewport (90%) → 700px (70%)
  assert.equal(clampSidePaneWidth(900, 1000), 700);
});

test('clampSidePaneWidth rounds to integer pixels', () => {
  assert.equal(clampSidePaneWidth(333.7, 1000), 334);
});

test('MIN_RATIO and MAX_RATIO export the expected band', () => {
  assert.equal(MIN_RATIO, 0.30);
  assert.equal(MAX_RATIO, 0.70);
});
