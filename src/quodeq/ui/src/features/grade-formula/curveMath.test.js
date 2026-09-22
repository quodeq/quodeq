import test from 'node:test';
import assert from 'node:assert/strict';
import { baseCurve, ceilingCurve } from './curveMath.js';

// ---------------------------------------------------------------------------
// baseCurve -- mirrors core/scoring/internals.py:46 (violation_base)
// ---------------------------------------------------------------------------

test('baseCurve: wv=0 is always 10 regardless of baseK', () => {
  assert.equal(baseCurve(0, 0.5), 10);
  assert.equal(baseCurve(0, 0), 10);
});

test('baseCurve: pinned value at a known (wv, baseK)', () => {
  // 10 / (1 + 0.1 * 5) = 10 / 1.5
  assert.ok(Math.abs(baseCurve(5, 0.1) - 10 / 1.5) < 1e-9);
});

test('baseCurve: increasing wv monotonically lowers the score', () => {
  const k = 0.2;
  assert.ok(baseCurve(1, k) > baseCurve(2, k));
  assert.ok(baseCurve(2, k) > baseCurve(10, k));
});

// ---------------------------------------------------------------------------
// ceilingCurve -- mirrors core/scoring/internals.py:77 (violation_ceiling)
// ---------------------------------------------------------------------------

test('ceilingCurve: wv=0 is always 10 regardless of ceilScale', () => {
  assert.equal(ceilingCurve(0, 2), 10);
  assert.equal(ceilingCurve(0, 0), 10);
});

test('ceilingCurve: pinned value at a known (wv, ceilScale)', () => {
  // 10 - log2(1 + 3) * 1.5 = 10 - 2 * 1.5 = 7
  assert.ok(Math.abs(ceilingCurve(3, 1.5) - 7) < 1e-9);
});

test('ceilingCurve: increasing wv monotonically lowers the ceiling', () => {
  const scale = 1;
  assert.ok(ceilingCurve(1, scale) > ceilingCurve(3, scale));
  assert.ok(ceilingCurve(3, scale) > ceilingCurve(7, scale));
});
