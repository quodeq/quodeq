import { describe, it, expect, vi, afterEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useMinimumHold } from './useMinimumHold.js';

// A warm boot releases the startup loader's data-hold almost at once, so
// the loader (and its tip) flashed for a frame. useMinimumHold keeps it up
// for a minimum time from mount; a slow boot is not lengthened.
describe('useMinimumHold', () => {
  afterEach(() => vi.useRealTimers());

  it('holds true until the minimum has passed when the value drops early', () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(({ v }) => useMinimumHold(v, 1000), { initialProps: { v: true } });
    rerender({ v: false });
    expect(result.current).toBe(true);
    act(() => { vi.advanceTimersByTime(900); });
    expect(result.current).toBe(true);
    act(() => { vi.advanceTimersByTime(100); });
    expect(result.current).toBe(false);
  });

  it('drops with the value once the minimum has already passed', () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(({ v }) => useMinimumHold(v, 1000), { initialProps: { v: true } });
    act(() => { vi.advanceTimersByTime(5000); });
    expect(result.current).toBe(true);
    rerender({ v: false });
    expect(result.current).toBe(false);
  });

  it('starting false never holds', () => {
    vi.useFakeTimers();
    const { result } = renderHook(({ v }) => useMinimumHold(v, 1000), { initialProps: { v: false } });
    expect(result.current).toBe(false);
  });
});
