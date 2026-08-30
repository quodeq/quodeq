import test from 'node:test';
import assert from 'node:assert/strict';
import { trendDomain, monotonePath } from './compareTrendModel.js';
import { scoreDomain } from '../../components/scoreChartHelpers.js';

// ---------------------------------------------------------------------------
// trendDomain
// ---------------------------------------------------------------------------

test('trendDomain: value bounds delegate to scoreDomain (dedup with the score charts)', () => {
  const a = [{ dateISO: '2024-01-01', value: 6.9 }, { dateISO: '2024-02-01', value: 7.7 }];
  const b = [{ dateISO: '2024-01-15', value: 8.2 }];
  const { v0, v1 } = trendDomain([a, b]);
  assert.deepEqual([v0, v1], scoreDomain([6.9, 7.7, 8.2]));
});

test('trendDomain: time bounds span the min/max timestamp across both series', () => {
  const a = [{ dateISO: '2024-03-01', value: 7 }];
  const b = [{ dateISO: '2024-01-01', value: 7 }, { dateISO: '2024-06-01', value: 7 }];
  const { t0, t1 } = trendDomain([a, b]);
  assert.equal(t0, Date.parse('2024-01-01'));
  assert.equal(t1, Date.parse('2024-06-01'));
});

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
