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

// Keys invalidated so far, as plain arrays for deep comparison.
function keysCalled(invalidateSpy) {
  return invalidateSpy.mock.calls.map((c) => c[0].queryKey);
}

// One refresh = one invalidation of the latest-scores key. Counting those
// counts refreshes without coupling the tests to how many scoped keys each
// refresh touches.
function refreshCount(invalidateSpy, project = 'p1') {
  const latestKey = JSON.stringify(projectKeys.scores(project, null));
  return keysCalled(invalidateSpy).filter((k) => JSON.stringify(k) === latestKey).length;
}

describe('useRunningRunsRefresh', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    import.meta.env.VITE_USE_SSE_EVENTS = 'false';
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('refreshes once on mount even when every run is terminal', () => {
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
    expect(refreshCount(invalidateSpy)).toBe(1);
    invalidateSpy.mockClear();
    // No further invalidations after mount -- nothing is in_progress, so
    // the polling interval doesn't run.
    act(() => {
      vi.advanceTimersByTime(IN_PROGRESS_POLL_MS * 3);
    });
    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it('scopes the refresh to latest keys, never the whole project subtree', () => {
    // Completed historical runs are immutable and their caches deliberately
    // frozen (see useDashboard). A subtree-wide invalidation here would mark
    // every cached run detail stale and reintroduce the background-refetch
    // dim on every pass through History.
    const { Wrapper, invalidateSpy } = makeWrapper();
    renderHook(
      () =>
        useRunningRunsRefresh({
          selectedProject: 'p1',
          availableRuns: [{ runId: 'r1', status: 'complete' }],
        }),
      { wrapper: Wrapper },
    );
    const keys = keysCalled(invalidateSpy);
    expect(keys).toContainEqual(projectKeys.scores('p1', null));
    expect(keys).toContainEqual(projectKeys.dashboard('p1', null));
    // Neither the bare subtree nor the completed run's own caches.
    expect(keys).not.toContainEqual(projectKeys.project('p1'));
    expect(keys).not.toContainEqual(projectKeys.dashboard('p1', 'r1'));
    expect(keys).not.toContainEqual(projectKeys.scores('p1', 'r1'));
  });

  it('keeps an in-progress run\'s own dashboard fresh while it lives', () => {
    const { Wrapper, invalidateSpy } = makeWrapper();
    renderHook(
      () =>
        useRunningRunsRefresh({
          selectedProject: 'p1',
          availableRuns: [
            { runId: 'r_live', status: 'in_progress' },
            { runId: 'r_done', status: 'complete' },
          ],
        }),
      { wrapper: Wrapper },
    );
    const keys = keysCalled(invalidateSpy);
    expect(keys).toContainEqual(projectKeys.dashboard('p1', 'r_live'));
    expect(keys).not.toContainEqual(projectKeys.dashboard('p1', 'r_done'));
  });

  it('refreshes on mount AND on each tick while a run is in_progress', () => {
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
    expect(refreshCount(invalidateSpy)).toBe(1);
    invalidateSpy.mockClear();
    // Then polling: 2 ticks within the advanced window.
    act(() => {
      vi.advanceTimersByTime(IN_PROGRESS_POLL_MS * 2 + 50);
    });
    expect(refreshCount(invalidateSpy)).toBe(2);
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
    // Mount-time refresh (1) + first poll tick (1) = 2 within the window.
    act(() => {
      vi.advanceTimersByTime(IN_PROGRESS_POLL_MS + 50);
    });
    expect(refreshCount(invalidateSpy)).toBe(2);
    invalidateSpy.mockClear();
    // Run terminates. Polling stops; selectedProject didn't change so the
    // mount-effect doesn't re-fire.
    rerender({ runs: [{ runId: 'r1', status: 'complete' }] });
    act(() => {
      vi.advanceTimersByTime(IN_PROGRESS_POLL_MS * 5);
    });
    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it('re-refreshes when the user switches to a different project', () => {
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
    expect(refreshCount(invalidateSpy, 'p1')).toBe(1);
    invalidateSpy.mockClear();
    rerender({ project: 'p2' });
    expect(refreshCount(invalidateSpy, 'p2')).toBe(1);
    expect(keysCalled(invalidateSpy)).toContainEqual(projectKeys.dashboard('p2', null));
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
    expect(refreshCount(invalidateSpy)).toBe(1);
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
    expect(refreshCount(invalidateSpy)).toBe(2);
  });

  // Task 17: source-aware cache keys. selectedSource must be folded into
  // every key this hook invalidates, so a refresh scoped to one source never
  // marks the other source's cache stale.
  describe('source-aware cache keys', () => {
    it("scopes invalidation to the 'local' keys by default", () => {
      const { Wrapper, invalidateSpy } = makeWrapper();
      renderHook(
        () =>
          useRunningRunsRefresh({
            selectedProject: 'p1',
            availableRuns: [{ runId: 'r1', status: 'complete' }],
          }),
        { wrapper: Wrapper },
      );
      const keys = keysCalled(invalidateSpy);
      expect(keys).toContainEqual(projectKeys.scores('p1', null, 'local'));
      expect(keys).toContainEqual(projectKeys.dashboard('p1', null, 'local'));
    });

    it("scopes invalidation to the 'shared' keys when selectedSource is 'shared'", () => {
      const { Wrapper, invalidateSpy } = makeWrapper();
      renderHook(
        () =>
          useRunningRunsRefresh({
            selectedProject: 'p1',
            selectedSource: 'shared',
            availableRuns: [{ runId: 'r1', status: 'complete' }],
          }),
        { wrapper: Wrapper },
      );
      const keys = keysCalled(invalidateSpy);
      expect(keys).toContainEqual(projectKeys.scores('p1', null, 'shared'));
      expect(keys).toContainEqual(projectKeys.dashboard('p1', null, 'shared'));
      // Never touches the local source's cache slot.
      expect(keys).not.toContainEqual(projectKeys.scores('p1', null, 'local'));
      expect(keys).not.toContainEqual(projectKeys.dashboard('p1', null, 'local'));
    });
  });
});
