import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useRunningRunsRefresh } from './useRunningRunsRefresh.js';
import { IN_PROGRESS_POLL_MS } from '../utils/runPolling.js';
import { projectKeys } from '../api/queryKeys.js';

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  const invalidateSpy = vi.spyOn(client, 'invalidateQueries');
  function Wrapper({ children }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }
  return { Wrapper, invalidateSpy };
}

describe('useRunningRunsRefresh', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('does not invalidate when every run is terminal', () => {
    const { Wrapper, invalidateSpy } = makeWrapper();
    renderHook(
      () =>
        useRunningRunsRefresh({
          selectedProject: 'p1',
          availableRuns: [{ runId: 'r1', status: 'complete' }],
        }),
      { wrapper: Wrapper },
    );
    act(() => {
      vi.advanceTimersByTime(IN_PROGRESS_POLL_MS * 3);
    });
    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it('invalidates on each tick while a run is in_progress', () => {
    const { Wrapper, invalidateSpy } = makeWrapper();
    renderHook(
      () =>
        useRunningRunsRefresh({
          selectedProject: 'p1',
          availableRuns: [
            { runId: 'r1', status: 'in_progress' },
            { runId: 'r0', status: 'complete' },
          ],
        }),
      { wrapper: Wrapper },
    );
    act(() => {
      vi.advanceTimersByTime(IN_PROGRESS_POLL_MS * 2 + 50);
    });
    expect(invalidateSpy).toHaveBeenCalledTimes(2);
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: projectKeys.project('p1'),
    });
  });

  it('stops invalidating once all runs become terminal', () => {
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { rerender } = renderHook(
      ({ runs }) =>
        useRunningRunsRefresh({ selectedProject: 'p1', availableRuns: runs }),
      {
        wrapper: Wrapper,
        initialProps: {
          runs: [{ runId: 'r1', status: 'in_progress' }],
        },
      },
    );
    act(() => {
      vi.advanceTimersByTime(IN_PROGRESS_POLL_MS + 50);
    });
    expect(invalidateSpy).toHaveBeenCalledTimes(1);
    invalidateSpy.mockClear();
    rerender({ runs: [{ runId: 'r1', status: 'complete' }] });
    act(() => {
      vi.advanceTimersByTime(IN_PROGRESS_POLL_MS * 5);
    });
    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it('does nothing without a selected project', () => {
    const { Wrapper, invalidateSpy } = makeWrapper();
    renderHook(
      () =>
        useRunningRunsRefresh({
          selectedProject: '',
          availableRuns: [{ runId: 'r1', status: 'in_progress' }],
        }),
      { wrapper: Wrapper },
    );
    act(() => {
      vi.advanceTimersByTime(IN_PROGRESS_POLL_MS * 3);
    });
    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});
