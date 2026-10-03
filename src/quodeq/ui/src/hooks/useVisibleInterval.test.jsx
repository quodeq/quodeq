import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { APP_VISIBILITY_EVENT } from '../constants.js';
import { resetAppVisibilityForTest } from '../utils/appVisibility.js';
import { useVisibleInterval } from './useVisibleInterval.js';

const POLL_MS = 1000;

function shellVisibility(hidden) {
  act(() => {
    window.dispatchEvent(new CustomEvent(APP_VISIBILITY_EVENT, { detail: { hidden } }));
  });
}

function advance(ms) {
  act(() => { vi.advanceTimersByTime(ms); });
}

describe('useVisibleInterval', () => {
  beforeEach(() => {
    resetAppVisibilityForTest();
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    resetAppVisibilityForTest();
  });

  it('ticks on the interval while visible', () => {
    const tick = vi.fn();
    renderHook(() => useVisibleInterval(tick, POLL_MS));

    expect(tick).not.toHaveBeenCalled();
    advance(POLL_MS * 3);
    expect(tick).toHaveBeenCalledTimes(3);
  });

  it('stops firing when the window goes hidden and fires once on return', () => {
    const tick = vi.fn();
    renderHook(() => useVisibleInterval(tick, POLL_MS));
    advance(POLL_MS);
    expect(tick).toHaveBeenCalledTimes(1);

    shellVisibility(true);
    advance(POLL_MS * 5);
    expect(tick).toHaveBeenCalledTimes(1);

    // Back in view: catch up immediately rather than make the user wait a
    // whole period for fresh data.
    shellVisibility(false);
    expect(tick).toHaveBeenCalledTimes(2);
    advance(POLL_MS);
    expect(tick).toHaveBeenCalledTimes(3);
  });

  it('never starts a timer when it mounts hidden', () => {
    const tick = vi.fn();
    shellVisibility(true);
    renderHook(() => useVisibleInterval(tick, POLL_MS));

    advance(POLL_MS * 5);
    expect(tick).not.toHaveBeenCalled();
  });

  it('runs no timer when the period is falsy', () => {
    const tick = vi.fn();
    renderHook(() => useVisibleInterval(tick, 0));

    advance(POLL_MS * 5);
    expect(tick).not.toHaveBeenCalled();
  });

  it('keeps the clock running when only the callback changes', () => {
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = renderHook(({ cb }) => useVisibleInterval(cb, POLL_MS), {
      initialProps: { cb: first },
    });

    advance(POLL_MS / 2);
    rerender({ cb: second });
    advance(POLL_MS / 2);

    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });

  it('clears its timer on unmount', () => {
    const tick = vi.fn();
    const { unmount } = renderHook(() => useVisibleInterval(tick, POLL_MS));

    unmount();
    advance(POLL_MS * 3);
    expect(tick).not.toHaveBeenCalled();
  });
});
