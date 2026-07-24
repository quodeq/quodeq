import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useOverviewReturnReconcile, TAB_OVERVIEW } from './useAppState.js';
import { useDashboard } from '../features/dashboard/hooks/useDashboard.js';
import { ApiProvider } from '../api/ApiContext.jsx';
import { projectKeys } from '../api/queryKeys.js';

// Task 2 (stacked on Task 1's scheduleDashboardReconcile): the Overview's
// useDashboard observer is mounted at the app root and never remounts on tab
// navigation, and the desktop pywebview window never fires the focus-refetch
// a browser tab gets on refocus. useOverviewReturnReconcile is the second
// layer -- an explicit active refetch of already-stale project queries when
// the user navigates BACK to the Overview, gated so it never re-downloads a
// fresh (unexpired staleTime) payload on every tab switch.

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
}

function renderReconcile(initialProps) {
  const client = makeClient();
  const spy = vi.spyOn(client, 'refetchQueries');
  const { result, rerender } = renderHook(
    (props) => useOverviewReturnReconcile(props),
    {
      wrapper: ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>,
      initialProps,
    },
  );
  return { client, spy, result, rerender };
}

describe('useOverviewReturnReconcile transition gating', () => {
  it('calls refetchQueries with {stale:true, type:"active"} and the project key on a transition INTO the overview tab', () => {
    const { spy, rerender } = renderReconcile({ activeTab: 'violations', selectedProject: 'p1', selectedSource: 'local' });
    expect(spy).not.toHaveBeenCalled();

    rerender({ activeTab: TAB_OVERVIEW, selectedProject: 'p1', selectedSource: 'local' });

    expect(spy).toHaveBeenCalledTimes(1);
    const arg = spy.mock.calls[0][0];
    expect(arg.stale).toBe(true);
    expect(arg.type).toBe('active');
    expect(arg.queryKey).toEqual(projectKeys.project('p1', 'local'));
  });

  it('does NOT call refetchQueries on initial mount even when the starting tab is overview', () => {
    const { spy } = renderReconcile({ activeTab: TAB_OVERVIEW, selectedProject: 'p1', selectedSource: 'local' });
    expect(spy).not.toHaveBeenCalled();
  });

  it('does NOT call refetchQueries on a transition between two non-overview tabs', () => {
    const { spy, rerender } = renderReconcile({ activeTab: 'violations', selectedProject: 'p1', selectedSource: 'local' });
    rerender({ activeTab: 'map', selectedProject: 'p1', selectedSource: 'local' });
    expect(spy).not.toHaveBeenCalled();
  });

  it('does NOT call refetchQueries on a transition AWAY from the overview tab', () => {
    const { spy, rerender } = renderReconcile({ activeTab: TAB_OVERVIEW, selectedProject: 'p1', selectedSource: 'local' });
    rerender({ activeTab: 'violations', selectedProject: 'p1', selectedSource: 'local' });
    expect(spy).not.toHaveBeenCalled();
  });

  it('does NOT call refetchQueries on a transition into overview when there is no selected project', () => {
    const { spy, rerender } = renderReconcile({ activeTab: 'violations', selectedProject: '', selectedSource: 'local' });
    rerender({ activeTab: TAB_OVERVIEW, selectedProject: '', selectedSource: 'local' });
    expect(spy).not.toHaveBeenCalled();
  });

  it('re-fires on a subsequent transition back into overview after leaving again', () => {
    const { spy, rerender } = renderReconcile({ activeTab: 'violations', selectedProject: 'p1', selectedSource: 'local' });
    rerender({ activeTab: TAB_OVERVIEW, selectedProject: 'p1', selectedSource: 'local' });
    expect(spy).toHaveBeenCalledTimes(1);
    rerender({ activeTab: 'violations', selectedProject: 'p1', selectedSource: 'local' });
    rerender({ activeTab: TAB_OVERVIEW, selectedProject: 'p1', selectedSource: 'local' });
    expect(spy).toHaveBeenCalledTimes(2);
  });
});

// Integration: prove the `stale: true` filter actually does the work end to
// end against a real useDashboard-mounted query, not just that the right
// arguments are passed. This is the seam the brief calls out explicitly: a
// FRESH query (within staleTime) must not trigger a re-download of the
// (potentially 10-20 MB) dashboard payload on a tab-switch round trip.
function makeFakeApi() {
  return {
    getDashboard: vi.fn(async (project, run) => ({
      project, run: run || 'latest', trend: [], summary: { score: 75 }, dimensions: [],
      selectedRun: { runId: 'r1', dateLabel: '2026-05-01' },
    })),
    sharedGetDashboard: vi.fn(),
    getProjectScores: vi.fn(async () => ({ accumulated: { score: 90 }, trend: [], availableRuns: [] })),
    sharedGetProjectScores: vi.fn(),
    sharedGetProjectInfo: vi.fn(),
  };
}

function useCombined({ activeTab, selectedProject, selectedSource }) {
  const dash = useDashboard({ selectedProject, selectedRun: null, selectedSource });
  useOverviewReturnReconcile({ activeTab, selectedProject, selectedSource });
  return dash;
}

function renderCombined(client, fakeApi, initialProps) {
  return renderHook((props) => useCombined(props), {
    wrapper: ({ children }) => (
      <QueryClientProvider client={client}>
        <ApiProvider value={fakeApi}>{children}</ApiProvider>
      </QueryClientProvider>
    ),
    initialProps,
  });
}

describe('useOverviewReturnReconcile integration with useDashboard (stale gating)', () => {
  it('does NOT refetch when the project query is still fresh (within staleTime)', async () => {
    const client = makeClient();
    const fakeApi = makeFakeApi();
    const { result, rerender } = renderCombined(client, fakeApi, {
      activeTab: 'violations', selectedProject: 'p1', selectedSource: 'local',
    });
    await waitFor(() => expect(result.current.dashboard).not.toBeNull());
    expect(fakeApi.getDashboard).toHaveBeenCalledTimes(1);

    rerender({ activeTab: TAB_OVERVIEW, selectedProject: 'p1', selectedSource: 'local' });
    // Give any errant refetch a chance to fire, then assert it didn't.
    await new Promise((r) => setTimeout(r, 50));
    expect(fakeApi.getDashboard).toHaveBeenCalledTimes(1);
  });

  it('DOES refetch when the project query was marked stale (refetchType:"none" invalidation, e.g. after a dismiss)', async () => {
    const client = makeClient();
    const fakeApi = makeFakeApi();
    const { result, rerender } = renderCombined(client, fakeApi, {
      activeTab: 'violations', selectedProject: 'p1', selectedSource: 'local',
    });
    await waitFor(() => expect(result.current.dashboard).not.toBeNull());
    expect(fakeApi.getDashboard).toHaveBeenCalledTimes(1);

    await act(async () => {
      await client.invalidateQueries({ queryKey: projectKeys.project('p1', 'local'), refetchType: 'none' });
    });

    rerender({ activeTab: TAB_OVERVIEW, selectedProject: 'p1', selectedSource: 'local' });

    await waitFor(() => expect(fakeApi.getDashboard).toHaveBeenCalledTimes(2));
  });
});
