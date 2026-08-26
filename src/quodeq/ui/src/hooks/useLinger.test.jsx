import { describe, it, expect, vi, afterEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useLinger } from './useLinger.js';

// The startup loader fades the instant its hold drops, but the page
// beneath needs a beat to finish committing (the recharts chart's first
// render measured ~200ms) — without a linger the fade reveals a chart-slot
// placeholder inside otherwise-real content. useLinger keeps the loader
// opaque for a fixed beat after the drop so the fade reveals a finished page.
describe('useLinger', () => {
  afterEach(() => vi.useRealTimers());

  it('passes true through immediately', () => {
    vi.useFakeTimers();
    const { result } = renderHook(({ v }) => useLinger(v, 250), { initialProps: { v: true } });
    expect(result.current).toBe(true);
  });

  it('keeps returning true for the linger window after the value drops', () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(({ v }) => useLinger(v, 250), { initialProps: { v: true } });
    rerender({ v: false });
    expect(result.current).toBe(true);
    act(() => { vi.advanceTimersByTime(200); });
    expect(result.current).toBe(true);
    act(() => { vi.advanceTimersByTime(100); });
    expect(result.current).toBe(false);
  });

  it('starting false never lingers', () => {
    vi.useFakeTimers();
    const { result } = renderHook(({ v }) => useLinger(v, 250), { initialProps: { v: false } });
    expect(result.current).toBe(false);
  });
});
