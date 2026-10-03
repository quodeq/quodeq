import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useDashboardPageState } from './useDashboardPageState.js';

// "No evaluations yet" is only true of a project without runs. A project
// with runs whose payloads are missing (a disabled scoped query, a timeout
// between retries) shows the skeleton or the error state instead.
const base = {
  runMode: false, dashboard: null, accumulated: null, loading: false, error: null,
  selectedProject: 'p1', selectedSource: 'local', selectedRunId: null,
};

describe('useDashboardPageState no-runs gate', () => {
  it('never shows the empty state for a project that has runs', () => {
    const { result } = renderHook(() => useDashboardPageState({ ...base, hasRuns: true }));
    expect(result.current.showNoRunsEmpty).toBe(false);
    expect(result.current.showOverviewSkeleton).toBe(true);
  });

  it('shows it for a project without runs once settled', () => {
    const { result } = renderHook(() => useDashboardPageState({ ...base, hasRuns: false }));
    expect(result.current.showNoRunsEmpty).toBe(true);
  });

  it('keeps a latched empty state through the load after the first run, then drops it once settled with runs', () => {
    // The transition a first evaluation makes: the empty state stays (dimmed)
    // while the payloads load rather than flashing a skeleton, and cannot
    // come back once the project is known to have runs.
    const { result, rerender } = renderHook((p) => useDashboardPageState(p), { initialProps: { ...base, hasRuns: false } });
    expect(result.current.showNoRunsEmpty).toBe(true);
    rerender({ ...base, hasRuns: true, loading: true });
    expect(result.current.showNoRunsEmpty).toBe(true);
    rerender({ ...base, hasRuns: true, loading: false });
    expect(result.current.showNoRunsEmpty).toBe(false);
    expect(result.current.showOverviewSkeleton).toBe(true);
  });
});
