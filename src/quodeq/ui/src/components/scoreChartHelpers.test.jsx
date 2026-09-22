import { describe, it, expect, vi, afterEach } from 'vitest';
import { waitFor } from '@testing-library/react';
import {
  scoreDomain, refLineValues, cssVar, clearCssVarCache, createCssVarStore,
} from './scoreChartHelpers.js';

// Regression coverage for the theme-invalidation mechanism itself (not just
// the pure helpers below): RunHistoryPanel/HistoryChartPanel/
// DimensionScoreHistoryPanel all re-read cssVar() on every render but never
// re-render on a theme switch by themselves — the ONLY thing that makes a
// chart pick up new colors is this module's MutationObserver clearing the
// cache when documentElement's data-theme attribute changes. No prior test
// exercised that observer at all, so a refactor that silently dropped it
// (e.g. moving observe() into a React effect that races 3 panels' unmount,
// or forgetting to call it) would ship with every existing test green.
describe('cssVar theme invalidation (regression: the MutationObserver must stay wired)', () => {
  const VAR = '--scoreChartHelpers-test-color';

  afterEach(() => {
    document.documentElement.style.removeProperty(VAR);
    document.documentElement.removeAttribute('data-theme');
    clearCssVarCache();
  });

  it('re-reads the computed value after a data-theme switch instead of serving the stale cached one', async () => {
    document.documentElement.style.setProperty(VAR, 'rgb(1, 2, 3)');
    expect(cssVar(VAR)).toBe('rgb(1, 2, 3)');
    // Cached: changing the CSS value alone must NOT be visible yet.
    document.documentElement.style.setProperty(VAR, 'rgb(4, 5, 6)');
    expect(cssVar(VAR)).toBe('rgb(1, 2, 3)');

    // Flipping data-theme is the only signal the cache watches.
    document.documentElement.setAttribute('data-theme', 'dark');

    await waitFor(() => expect(cssVar(VAR)).toBe('rgb(4, 5, 6)'));
  });

  it('serves repeat reads from the cache without re-invoking getComputedStyle', () => {
    document.documentElement.style.setProperty(VAR, 'rgb(9, 9, 9)');
    const spy = vi.spyOn(window, 'getComputedStyle');
    expect(cssVar(VAR)).toBe('rgb(9, 9, 9)');
    expect(spy).toHaveBeenCalledTimes(1);
    expect(cssVar(VAR)).toBe('rgb(9, 9, 9)');
    expect(cssVar(VAR)).toBe('rgb(9, 9, 9)');
    expect(spy).toHaveBeenCalledTimes(1); // still just the first, cold read
    spy.mockRestore();
  });

  it('clearCssVarCache forces the next read to go back to the DOM', () => {
    document.documentElement.style.setProperty(VAR, 'rgb(1, 1, 1)');
    expect(cssVar(VAR)).toBe('rgb(1, 1, 1)');
    document.documentElement.style.setProperty(VAR, 'rgb(2, 2, 2)');
    clearCssVarCache();
    expect(cssVar(VAR)).toBe('rgb(2, 2, 2)');
  });
});

describe('createCssVarStore', () => {
  it('two instances never share a cache or an observer', async () => {
    const a = createCssVarStore({ doc: document });
    const b = createCssVarStore({ doc: document });
    a.observe();
    b.observe();
    try {
      document.documentElement.style.setProperty('--store-isolation-test', 'rgb(1, 1, 1)');
      expect(a.cssVar('--store-isolation-test')).toBe('rgb(1, 1, 1)');
      expect(b.cssVar('--store-isolation-test')).toBe('rgb(1, 1, 1)');

      document.documentElement.style.setProperty('--store-isolation-test', 'rgb(2, 2, 2)');
      a.clear(); // only a's cache is invalidated
      expect(a.cssVar('--store-isolation-test')).toBe('rgb(2, 2, 2)');
      expect(b.cssVar('--store-isolation-test')).toBe('rgb(1, 1, 1)');
    } finally {
      a.disconnect();
      b.disconnect();
      document.documentElement.style.removeProperty('--store-isolation-test');
    }
  });

  it('observe() is idempotent: calling it twice attaches only one observer', async () => {
    const store = createCssVarStore({ doc: document });
    store.observe();
    store.observe(); // must be a no-op, not a second observer
    try {
      document.documentElement.style.setProperty('--observe-idempotent-test', 'rgb(1, 1, 1)');
      expect(store.cssVar('--observe-idempotent-test')).toBe('rgb(1, 1, 1)');
      document.documentElement.style.setProperty('--observe-idempotent-test', 'rgb(2, 2, 2)');
      document.documentElement.setAttribute('data-theme', 'dark');
      await waitFor(() => expect(store.cssVar('--observe-idempotent-test')).toBe('rgb(2, 2, 2)'));
    } finally {
      store.disconnect();
      document.documentElement.removeAttribute('data-theme');
      document.documentElement.style.removeProperty('--observe-idempotent-test');
    }
  });
});

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
