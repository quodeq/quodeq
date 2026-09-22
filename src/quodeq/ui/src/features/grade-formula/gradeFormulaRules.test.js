import test from 'node:test';
import assert from 'node:assert/strict';
import { clampFloors } from './gradeFormulaRules.js';

const DRAFT = { floorMinor: 8, floorMajor: 5, baseK: 0.1 };

test('clampFloors: floorMinor cannot drop below floorMajor', () => {
  assert.deepEqual(clampFloors(DRAFT, { floorMinor: 3 }), { floorMinor: 5 });
});

test('clampFloors: floorMinor passes through unchanged when already above floorMajor', () => {
  assert.deepEqual(clampFloors(DRAFT, { floorMinor: 9 }), { floorMinor: 9 });
});

test('clampFloors: floorMajor cannot rise above floorMinor', () => {
  assert.deepEqual(clampFloors(DRAFT, { floorMajor: 10 }), { floorMajor: 8 });
});

test('clampFloors: floorMajor passes through unchanged when already below floorMinor', () => {
  assert.deepEqual(clampFloors(DRAFT, { floorMajor: 2 }), { floorMajor: 2 });
});

test('clampFloors: is a no-op on a patch that touches neither floor', () => {
  const patch = { gradeThresholds: [[9, 'Exemplary']] };
  assert.equal(clampFloors(DRAFT, patch), patch);
});

test('clampFloors: is a no-op on a patch that touches an unrelated field', () => {
  const patch = { baseK: 0.5 };
  assert.equal(clampFloors(DRAFT, patch), patch);
});

test('clampFloors: passes the patch through when draft is not yet loaded', () => {
  const patch = { floorMinor: 3 };
  assert.equal(clampFloors(null, patch), patch);
});
