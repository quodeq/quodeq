import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { easeInOut, lerpTransform, useTweenedTransform, PACK_TWEEN_MS } from './packTween.js';

const A = { k: 1, tx: 0, ty: 0 };
const B = { k: 3, tx: -100, ty: -50 };
const HALF = 0.5;

describe('easeInOut', () => {
  it('is clamped, symmetric and passes through the midpoint', () => {
    expect(easeInOut(-1)).toBe(0);
    expect(easeInOut(2)).toBe(1);
    expect(easeInOut(HALF)).toBeCloseTo(HALF);
    expect(easeInOut(0.25)).toBeCloseTo(1 - easeInOut(0.75));
  });
});

describe('lerpTransform', () => {
  it('interpolates every component', () => {
    expect(lerpTransform(A, B, 0)).toEqual(A);
    expect(lerpTransform(A, B, 1)).toEqual(B);
    expect(lerpTransform(A, B, HALF)).toEqual({ k: 2, tx: -50, ty: -25 });
  });
});

// Drive requestAnimationFrame by hand: each `tick(ms)` runs the queued
// frame with a clock advanced by that much.
function fakeFrames() {
  let now = 0;
  let queued = null;
  vi.stubGlobal('requestAnimationFrame', (cb) => { queued = cb; return 1; });
  vi.stubGlobal('cancelAnimationFrame', () => { queued = null; });
  vi.spyOn(performance, 'now').mockImplementation(() => now);
  vi.stubGlobal('matchMedia', () => ({ matches: false }));
  return {
    tick(ms) {
      now += ms;
      const cb = queued;
      queued = null;
      cb?.(now);
    },
    hasFrame: () => queued !== null,
  };
}

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe('useTweenedTransform', () => {
  it('eases from the previous transform to the target over the tween window', () => {
    const frames = fakeFrames();
    const skip = { current: false };
    const { result, rerender } = renderHook(({ target }) => useTweenedTransform(target, skip), { initialProps: { target: A } });
    expect(result.current).toBe(A);

    rerender({ target: B });
    expect(result.current).toBe(A);
    act(() => frames.tick(PACK_TWEEN_MS / 2));
    expect(result.current.k).toBeGreaterThan(A.k);
    expect(result.current.k).toBeLessThan(B.k);
    act(() => frames.tick(PACK_TWEEN_MS));
    expect(result.current).toBe(B);
    expect(frames.hasFrame()).toBe(false);
  });

  it('snaps when transitions are skipped or motion is reduced', () => {
    const frames = fakeFrames();
    const skip = { current: true };
    const { result, rerender } = renderHook(({ target }) => useTweenedTransform(target, skip), { initialProps: { target: A } });
    rerender({ target: B });
    expect(result.current).toBe(B);
    expect(frames.hasFrame()).toBe(false);

    skip.current = false;
    vi.stubGlobal('matchMedia', () => ({ matches: true }));
    rerender({ target: A });
    expect(result.current).toBe(A);
    expect(frames.hasFrame()).toBe(false);
  });

  // The worker reply swaps the placeholder root for the real one; the focus
  // transform is rebuilt with the same values. The canvas treats
  // `shown === target` as "settled", so the new object must be adopted.
  it('adopts an equal-valued target without animating', () => {
    const frames = fakeFrames();
    const skip = { current: false };
    const { result, rerender } = renderHook(({ target }) => useTweenedTransform(target, skip), { initialProps: { target: A } });
    const sameAsA = { ...A };
    rerender({ target: sameAsA });
    expect(result.current).toBe(sameAsA);
    expect(frames.hasFrame()).toBe(false);
  });
});
