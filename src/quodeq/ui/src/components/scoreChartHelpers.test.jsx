import { describe, it, expect } from 'vitest';
import { scoreDomain, refLineValues } from './scoreChartHelpers.js';

describe('scoreDomain', () => {
  it('pads the data range by half a point and rounds outward', () => {
    // 6.9-8.2 must NOT flatten onto a 0-10 axis: floor(6.4)=6, ceil(8.7)=9.
    expect(scoreDomain([6.9, 7.7, 8.2])).toEqual([6, 9]);
  });

  it('clamps to the 0-10 score scale', () => {
    expect(scoreDomain([0.2, 0.4])).toEqual([0, 1]);
    expect(scoreDomain([9.8, 10])).toEqual([9, 10]);
  });

  it('keeps a non-empty span for flat data', () => {
    const [lo, hi] = scoreDomain([7.0, 7.0, 7.0]);
    expect(hi).toBeGreaterThan(lo);
    expect(lo).toBeLessThanOrEqual(7.0);
    expect(hi).toBeGreaterThanOrEqual(7.0);
  });

  it('falls back to the full scale with no finite values', () => {
    expect(scoreDomain([])).toEqual([0, 10]);
    expect(scoreDomain([NaN, undefined, null])).toEqual([0, 10]);
  });

  it('never renders an empty or full bar: bounds sit strictly outside the data', () => {
    const values = [6.9, 7.5, 8.2];
    const [lo, hi] = scoreDomain(values);
    expect(lo).toBeLessThan(Math.min(...values));
    expect(hi).toBeGreaterThan(Math.max(...values));
  });
});

describe('refLineValues', () => {
  it('returns the bounds plus quarter divisions', () => {
    expect(refLineValues([6, 9])).toEqual([6, 6.75, 7.5, 8.25, 9]);
    expect(refLineValues([0, 10])).toEqual([0, 2.5, 5, 7.5, 10]);
  });
});
