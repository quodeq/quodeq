import test from 'node:test';
import assert from 'node:assert/strict';
import { monotonePath, monotoneAt, smoothSeries, stepValueAt } from './compareTrendModel.js';

// ---------------------------------------------------------------------------
// monotonePath — exact `d`-string (rounding + spline math frozen)
// ---------------------------------------------------------------------------

test('monotonePath: empty/single-point input renders no path', () => {
  assert.equal(monotonePath([]), '');
  assert.equal(monotonePath([[0, 0]]), '');
});

test('monotonePath: two points render a straight line segment', () => {
  assert.equal(monotonePath([[5, 5], [5, 7]]), 'M5.0,5.0 L5.0,7.0');
});

test('monotonePath: three points, exact curve through a peak', () => {
  assert.equal(
    monotonePath([[0, 0], [10, 10], [20, 0]]),
    'M0.0,0.0 C3.3,3.3 6.7,10.0 10.0,10.0 C13.3,10.0 16.7,3.3 20.0,0.0',
  );
});

test('monotonePath: a straight run of points stays exactly straight', () => {
  assert.equal(
    monotonePath([[0, 0], [10, 5], [20, 10], [30, 15]]),
    'M0.0,0.0 C3.3,1.7 6.7,3.3 10.0,5.0 C13.3,6.7 16.7,8.3 20.0,10.0 C23.3,11.7 26.7,13.3 30.0,15.0',
  );
});

test('monotonePath: slope sign-change guard zeroes the tangent on a plateau', () => {
  // Flat then flat again: slope on both sides is 0, so the sign-change guard
  // (slope[i-1] * slope[i] <= 0) fires on 0 * 0 and must not divide by zero.
  assert.equal(
    monotonePath([[0, 0], [10, 0], [20, 0]]),
    'M0.0,0.0 C3.3,0.0 6.7,0.0 10.0,0.0 C13.3,0.0 16.7,0.0 20.0,0.0',
  );
});

test('monotonePath: duplicate-timestamp guard (dx[i] || 1) avoids a div-by-zero slope', () => {
  // First segment has dx=0 (two points at the same x) — without `|| 1` the
  // slope would be Infinity/NaN and poison the tangent computation.
  assert.equal(
    monotonePath([[0, 0], [0, 5], [10, 10]]),
    'M0.0,0.0 C0.0,0.0 0.0,5.0 0.0,5.0 C3.3,9.2 6.7,8.3 10.0,10.0',
  );
});

test('monotonePath: a 50-point series starts at the first point and emits one curve per pair', () => {
  const pts = Array.from({ length: 50 }, (_, i) => [i * 10, Math.sin(i) * 5 + 10]);
  const result = monotonePath(pts);
  // Shape check, not an exact-output lock: the start command and the
  // one-C-segment-per-pair structure are what callers depend on.
  assert.ok(result.startsWith('M0.0,10.0'));
  assert.ok(result.includes(' C'));
  assert.equal(result.split(' C').length - 1, 49); // one C-segment per point pair
});

// ---------------------------------------------------------------------------
// monotoneAt / smoothSeries / stepValueAt
// ---------------------------------------------------------------------------

test('monotoneAt: passes through every point and is null outside the span', () => {
  const pts = [[0, 10], [10, 20], [20, 15], [30, 30]];
  for (const [x, y] of pts) assert.ok(Math.abs(monotoneAt(pts, x) - y) < 1e-9);
  assert.equal(monotoneAt(pts, -1), null);
  assert.equal(monotoneAt(pts, 31), null);
});

test('monotoneAt: never overshoots a peak', () => {
  const pts = [[0, 0], [10, 10], [20, 0]];
  for (let x = 0; x <= 20; x += 0.5) assert.ok(monotoneAt(pts, x) <= 10 + 1e-9);
});

test('smoothSeries: lags the raw values but pins the last point to the real score', () => {
  const day = 86400000;
  const out = smoothSeries([{ t: 0, v: 5 }, { t: day, v: 9 }, { t: 2 * day, v: 9 }, { t: 3 * day, v: 4 }], 7 * day);
  assert.equal(out[0].v, 5);
  assert.ok(out[1].v > 5 && out[1].v < 9);
  assert.deepEqual(out.at(-1), { t: 3 * day, v: 4 });
});

test('stepValueAt: the value in force, null before the first point', () => {
  const pts = [{ t: 10, v: 6 }, { t: 20, v: 8 }];
  assert.equal(stepValueAt(pts, 5), null);
  assert.equal(stepValueAt(pts, 15), 6);
  assert.equal(stepValueAt(pts, 25), 8);
});
