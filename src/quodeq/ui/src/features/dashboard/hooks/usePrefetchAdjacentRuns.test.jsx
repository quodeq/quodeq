import { renderHook } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { usePrefetchAdjacentRuns } from './usePrefetchAdjacentRuns.js';
import { usePrefetchRun } from './usePrefetchRun.js';

vi.mock('./usePrefetchRun.js', () => ({
  usePrefetchRun: vi.fn(),
}));

const AVAILABLE_RUNS = [
  { runId: 'r3' },
  { runId: 'r2' },
  { runId: 'r1' },
];

describe('usePrefetchAdjacentRuns', () => {
  let prefetchRun;

  beforeEach(() => {
    vi.clearAllMocks();
    prefetchRun = vi.fn();
    usePrefetchRun.mockReturnValue({ prefetchRun });
  });

  it('prefetches the previous run on hover', () => {
    const { result } = renderHook(() =>
      usePrefetchAdjacentRuns({ selectedProject: 'p1', availableRuns: AVAILABLE_RUNS, overviewRunIndex: 1 }),
    );
    result.current.onPrevHover();
    expect(prefetchRun).toHaveBeenCalledWith('r1');
  });

  it('prefetches the next run on hover', () => {
    const { result } = renderHook(() =>
      usePrefetchAdjacentRuns({ selectedProject: 'p1', availableRuns: AVAILABLE_RUNS, overviewRunIndex: 1 }),
    );
    result.current.onNextHover();
    expect(prefetchRun).toHaveBeenCalledWith('r3');
  });

  it('prefetches the latest run on hover', () => {
    const { result } = renderHook(() =>
      usePrefetchAdjacentRuns({ selectedProject: 'p1', availableRuns: AVAILABLE_RUNS, overviewRunIndex: 1 }),
    );
    result.current.onLatestHover();
    expect(prefetchRun).toHaveBeenCalledWith('r3');
  });

  // Task 17: source-aware fetch selection. The underlying usePrefetchRun
  // hook must be constructed with the caller's selectedSource so hover
  // prefetches never warm the wrong source's cache slot.
  describe('source-aware fetch selection', () => {
    it("passes 'local' through to usePrefetchRun by default", () => {
      renderHook(() =>
        usePrefetchAdjacentRuns({ selectedProject: 'p1', availableRuns: AVAILABLE_RUNS, overviewRunIndex: 1 }),
      );
      expect(usePrefetchRun).toHaveBeenCalledWith('p1', 'local');
    });

    it("passes 'shared' through to usePrefetchRun when selectedSource is 'shared'", () => {
      renderHook(() =>
        usePrefetchAdjacentRuns({
          selectedProject: 'p1',
          selectedSource: 'shared',
          availableRuns: AVAILABLE_RUNS,
          overviewRunIndex: 1,
        }),
      );
      expect(usePrefetchRun).toHaveBeenCalledWith('p1', 'shared');
    });
  });
});
