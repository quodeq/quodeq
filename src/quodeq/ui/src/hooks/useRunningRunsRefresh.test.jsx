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
    import.meta.env.VITE_USE_SSE_EVENTS = 'false';
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('invalidates once on mount even when every run is terminal', () => {
    // Mount-time refresh fires regardless of polling state -- the user just
    // navigated to History and wants the latest data right now, not on the
    // next poll tick (which never comes when nothing is in_progress).
    const { Wrapper, invalidateSpy } = makeWrapper();
    renderHook(
      () =>
        useRunningRunsRefresh({
          selectedProject: 'p1',
          availableRuns: [{ runId: 'r1', status: 'complete' }],
        }),
      { wrapper: Wrapper },
    );
    expect(invalidateSpy).toHaveBeenCalledTimes(1);
    invalidateSpy.mockClear();
    // No further invalidations after mount -- nothing is in_progress, so
    // the polling interval doesn't run.
    act(() => {
      vi.advanceTimersByTime(IN_PROGRESS_POLL_MS * 3);
    });
    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it('invalidates on mount AND on each tick while a run is in_progress', () => {
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
    // Mount-time refresh fires immediately.
    expect(invalidateSpy).toHaveBeenCalledTimes(1);
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: projectKeys.project('p1'),
    });
    invalidateSpy.mockClear();
    // Then polling: 2 ticks within the advanced window.
    act(() => {
      vi.advanceTimersByTime(IN_PROGRESS_POLL_MS * 2 + 50);
    });
    expect(invalidateSpy).toHaveBeenCalledTimes(2);
  });

  it('stops polling once all runs become terminal (mount-refresh aside)', () => {
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
    // Mount-time invalidate (1) + first poll tick (1) = 2 within the window.
    act(() => {
      vi.advanceTimersByTime(IN_PROGRESS_POLL_MS + 50);
    });
    expect(invalidateSpy).toHaveBeenCalledTimes(2);
    invalidateSpy.mockClear();
    // Run terminates. Polling stops; selectedProject didn't change so the
    // mount-effect doesn't re-fire.
    rerender({ runs: [{ runId: 'r1', status: 'complete' }] });
    act(() => {
      vi.advanceTimersByTime(IN_PROGRESS_POLL_MS * 5);
    });
    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it('re-invalidates when the user switches to a different project', () => {
    // Navigating between projects (or back to History after viewing a
    // different one) should re-trigger the mount-time refresh so the new
    // project's data is current.
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { rerender } = renderHook(
      ({ project }) =>
        useRunningRunsRefresh({
          selectedProject: project,
          availableRuns: [{ runId: 'r1', status: 'complete' }],
        }),
      {
        wrapper: Wrapper,
        initialProps: { project: 'p1' },
      },
    );
    expect(invalidateSpy).toHaveBeenCalledTimes(1);
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: projectKeys.project('p1'),
    });
    invalidateSpy.mockClear();
    rerender({ project: 'p2' });
    expect(invalidateSpy).toHaveBeenCalledTimes(1);
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: projectKeys.project('p2'),
    });
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

  it('mount-time refresh fires regardless of VITE_USE_SSE_EVENTS', () => {
    import.meta.env.VITE_USE_SSE_EVENTS = 'true';
    const { Wrapper, invalidateSpy } = makeWrapper();
    renderHook(
      () =>
        useRunningRunsRefresh({
          selectedProject: 'p1',
          availableRuns: [{ runId: 'r1', status: 'in_progress' }],
        }),
      { wrapper: Wrapper },
    );
    expect(invalidateSpy).toHaveBeenCalledTimes(1);
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: projectKeys.project('p1'),
    });
  });

  it('suppresses recurring poll when VITE_USE_SSE_EVENTS=true', () => {
    import.meta.env.VITE_USE_SSE_EVENTS = 'true';
    const { Wrapper, invalidateSpy } = makeWrapper();
    renderHook(
      () =>
        useRunningRunsRefresh({
          selectedProject: 'p1',
          availableRuns: [{ runId: 'r1', status: 'in_progress' }],
        }),
      { wrapper: Wrapper },
    );
    invalidateSpy.mockClear(); // ignore the mount-time refresh
    act(() => {
      vi.advanceTimersByTime(IN_PROGRESS_POLL_MS * 5);
    });
    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it('still polls when VITE_USE_SSE_EVENTS is not "true"', () => {
    import.meta.env.VITE_USE_SSE_EVENTS = 'false';
    const { Wrapper, invalidateSpy } = makeWrapper();
    renderHook(
      () =>
        useRunningRunsRefresh({
          selectedProject: 'p1',
          availableRuns: [{ runId: 'r1', status: 'in_progress' }],
        }),
      { wrapper: Wrapper },
    );
    invalidateSpy.mockClear();
    act(() => {
      vi.advanceTimersByTime(IN_PROGRESS_POLL_MS * 2 + 50);
    });
    expect(invalidateSpy).toHaveBeenCalledTimes(2);
  });
});
