import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useOverviewReturnReconcile, resolveActiveTab, TAB_OVERVIEW } from './useAppState.js';
import { useNavStack } from './useNavStack.js';
import { useDashboard } from '../features/dashboard/hooks/useDashboard.js';
import { ApiProvider } from '../api/ApiContext.jsx';
import { projectKeys } from '../api/queryKeys.js';

// Split from useAppState.test.jsx: useOverviewReturnReconcile's transition
// gating, the untagged-drill-down-page regression, and its integration with
// useDashboard's stale gating.

// useAppState composes useEvaluationLifecycle (-> useEvaluation) and
// useServerHealth. Mocked the same way useEvaluationLifecycle.test.jsx mocks
// useEvaluation, so the eval-completion regression below can drive `job`
// directly without a real evaluation API, and without useServerHealth's
// real network polling.
vi.mock('../features/evaluation/hooks/useEvaluation.js', () => ({
  useEvaluation: () => ({
    job: null, jobError: null, liveViolations: {},
    startEvaluation: vi.fn(), clearJob: vi.fn(), cancelEvaluation: vi.fn(),
    startedProject: null,
  }),
  LOCAL_API_PROVIDERS: new Set(['ollama', 'llamacpp', 'omlx']),
}));
vi.mock('./useServerHealth.js', () => ({
  useServerHealth: () => [true, vi.fn(), null],
}));

// Task 2 (stacked on Task 1's scheduleDashboardReconcile): the Overview's
// useDashboard observer is mounted at the app root and never remounts on tab
// navigation, and the desktop pywebview window never fires the focus-refetch
// a browser tab gets on refocus. useOverviewReturnReconcile is the second
// layer -- an explicit active refetch of already-stale project queries when
// the user navigates BACK to the Overview, gated so it never re-downloads a
// fresh (unexpired staleTime) payload on every tab switch.
//
// Gates on `rootTab` (navStack[0].page), NOT the derived `activeTab` --
// `activeTab` defaults any untagged/unknown drill-down page (e.g.
// ExplorerPage's onPrincipleClick -> 'evalprinciple', handleCardNavigate ->
// 'file', both pushed without a `sourceTab`) to TAB_OVERVIEW, which would
// misfire a real refetch mid-triage inside Violations/Map. `navStack[0].page`
// is stable across drill-down depth because navPush only appends.

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
    const { spy, rerender } = renderReconcile({ rootTab: 'violations', selectedProject: 'p1', selectedSource: 'local' });
    expect(spy).not.toHaveBeenCalled();

    rerender({ rootTab: TAB_OVERVIEW, selectedProject: 'p1', selectedSource: 'local' });

    expect(spy).toHaveBeenCalledTimes(1);
    const arg = spy.mock.calls[0][0];
    expect(arg.stale).toBe(true);
    expect(arg.type).toBe('active');
    expect(arg.queryKey).toEqual(projectKeys.project('p1', 'local'));
  });

  it('does NOT call refetchQueries on initial mount even when the starting tab is overview', () => {
    const { spy } = renderReconcile({ rootTab: TAB_OVERVIEW, selectedProject: 'p1', selectedSource: 'local' });
    expect(spy).not.toHaveBeenCalled();
  });

  it('does NOT call refetchQueries on a transition between two non-overview tabs', () => {
    const { spy, rerender } = renderReconcile({ rootTab: 'violations', selectedProject: 'p1', selectedSource: 'local' });
    rerender({ rootTab: 'map', selectedProject: 'p1', selectedSource: 'local' });
    expect(spy).not.toHaveBeenCalled();
  });

  it('does NOT call refetchQueries on a transition AWAY from the overview tab', () => {
    const { spy, rerender } = renderReconcile({ rootTab: TAB_OVERVIEW, selectedProject: 'p1', selectedSource: 'local' });
    rerender({ rootTab: 'violations', selectedProject: 'p1', selectedSource: 'local' });
    expect(spy).not.toHaveBeenCalled();
  });

  it('does NOT call refetchQueries on a transition into overview when there is no selected project', () => {
    const { spy, rerender } = renderReconcile({ rootTab: 'violations', selectedProject: '', selectedSource: 'local' });
    rerender({ rootTab: TAB_OVERVIEW, selectedProject: '', selectedSource: 'local' });
    expect(spy).not.toHaveBeenCalled();
  });

  it('re-fires on a subsequent transition back into overview after leaving again', () => {
    const { spy, rerender } = renderReconcile({ rootTab: 'violations', selectedProject: 'p1', selectedSource: 'local' });
    rerender({ rootTab: TAB_OVERVIEW, selectedProject: 'p1', selectedSource: 'local' });
    expect(spy).toHaveBeenCalledTimes(1);
    rerender({ rootTab: 'violations', selectedProject: 'p1', selectedSource: 'local' });
    rerender({ rootTab: TAB_OVERVIEW, selectedProject: 'p1', selectedSource: 'local' });
    expect(spy).toHaveBeenCalledTimes(2);
  });
});

// Regression (reviewer finding): a drill-down page pushed without a
// `sourceTab` -- exactly what ExplorerPage.jsx's onPrincipleClick
// ('evalprinciple') and handleCardNavigate ('file') do -- must NOT be
// misread as "the user returned to the Overview". The old implementation
// consumed the derived `activeTab`, whose fallback bucket defaults any
// untagged/unknown page to TAB_OVERVIEW; drilling from Violations into an
// untagged 'evalprinciple'/'file' page flipped activeTab to 'overview' while
// the user was still mid-triage, misfiring a real refetch of the (10-20 MB)
// payload. This composes the REAL useNavStack with the hook, replaying the
// exact push sequence from the bug report, and asserts navStack[0].page
// (rootTab) never leaves 'violations' -- so no refetch fires.
describe('useOverviewReturnReconcile regression: untagged drill-down pages do not misfire', () => {
  function fakeHistoryAdapter() {
    return { pushState: vi.fn(), replaceState: vi.fn(), back: vi.fn(), go: vi.fn() };
  }

  function useRealNavRootTab() {
    const { navStack, navTab, navPush } = useNavStack({ historyAdapter: fakeHistoryAdapter() });
    return { rootTab: navStack[0]?.page, navStack, navTab, navPush };
  }

  function renderScenario() {
    const client = makeClient();
    const spy = vi.spyOn(client, 'refetchQueries');
    const { result } = renderHook(
      () => {
        const nav = useRealNavRootTab();
        useOverviewReturnReconcile({ rootTab: nav.rootTab, selectedProject: 'p1', selectedSource: 'local' });
        return nav;
      },
      { wrapper: ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider> },
    );
    return { result, spy };
  }

  it('does NOT refetch when drilling from Violations into an untagged evalprinciple page (ExplorerPage.onPrincipleClick)', () => {
    const { result, spy } = renderScenario();

    act(() => { result.current.navTab('violations'); });
    expect(result.current.rootTab).toBe('violations');

    // ExplorerPage mounted with sourceTab, as App.jsx wires it.
    act(() => { result.current.navPush({ page: 'explorer', sourceTab: 'violations', dimension: 'Security' }); });
    expect(result.current.rootTab).toBe('violations');

    // ExplorerPage.onPrincipleClick -> onNavigate('evalprinciple', { evalPrincipal }) -- NO sourceTab.
    act(() => { result.current.navPush({ page: 'evalprinciple', evalPrincipal: { principle: 'P' } }); });

    expect(result.current.rootTab).toBe('violations'); // never misclassified as overview
    expect(spy).not.toHaveBeenCalled();
  });

  it('does NOT refetch when drilling from Violations into an untagged file page (ExplorerPage.handleCardNavigate)', () => {
    const { result, spy } = renderScenario();

    act(() => { result.current.navTab('violations'); });
    act(() => { result.current.navPush({ page: 'explorer', sourceTab: 'violations', dimension: 'Security' }); });
    // ExplorerPage.handleCardNavigate -> onNavigate('file', { file, severityFilter, runId, dateLabel }) -- NO sourceTab.
    act(() => { result.current.navPush({ page: 'file', file: { path: 'a.py' }, severityFilter: 'all' }); });

    expect(result.current.rootTab).toBe('violations');
    expect(spy).not.toHaveBeenCalled();
  });

  // Documents WHY rootTab (not activeTab) is required: resolveActiveTab,
  // called directly against the exact untagged 'evalprinciple' page
  // ExplorerPage.onPrincipleClick pushes, resolves to TAB_OVERVIEW -- the
  // misclassification the reviewer flagged. Intentional: see the doc
  // comment on resolveActiveTab.
  it('resolveActiveTab misclassifies the same untagged page as overview', () => {
    const activePage = { page: 'evalprinciple', evalPrincipal: { principle: 'P' } };
    expect(resolveActiveTab(activePage)).toBe(TAB_OVERVIEW);
  });

  // Direct coverage of resolveActiveTab's other branches.
  it('resolveActiveTab: a known top-level page passes through', () => {
    expect(resolveActiveTab({ page: 'violations' })).toBe('violations');
  });

  it('resolveActiveTab: falls back to sourceTab when that is itself a known tab', () => {
    expect(resolveActiveTab({ page: 'explorer', sourceTab: 'violations' })).toBe('violations');
  });

  it('resolveActiveTab: an unknown page with no usable sourceTab falls back to history for history-run', () => {
    expect(resolveActiveTab({ page: 'history-run' })).toBe('history');
  });

  it('resolveActiveTab: an unknown page with an unknown/empty sourceTab defaults to overview', () => {
    expect(resolveActiveTab({ page: 'evalprinciple', sourceTab: '' })).toBe(TAB_OVERVIEW);
    expect(resolveActiveTab({ page: 'evalprinciple', sourceTab: 'not-a-tab' })).toBe(TAB_OVERVIEW);
  });

  it('still refetches on a genuine return to Overview after the same drill-down', () => {
    const { result, spy } = renderScenario();

    act(() => { result.current.navTab('violations'); });
    act(() => { result.current.navPush({ page: 'explorer', sourceTab: 'violations', dimension: 'Security' }); });
    act(() => { result.current.navPush({ page: 'evalprinciple', evalPrincipal: { principle: 'P' } }); });
    expect(spy).not.toHaveBeenCalled();

    // User backs out and picks the Overview tab from the sidebar.
    act(() => { result.current.navTab('overview'); });

    expect(result.current.rootTab).toBe(TAB_OVERVIEW);
    expect(spy).toHaveBeenCalledTimes(1);
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

function useCombined({ rootTab, selectedProject, selectedSource }) {
  const dash = useDashboard({ selectedProject, selectedRun: null, selectedSource });
  useOverviewReturnReconcile({ rootTab, selectedProject, selectedSource });
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
      rootTab: 'violations', selectedProject: 'p1', selectedSource: 'local',
    });
    await waitFor(() => expect(result.current.dashboard).not.toBeNull());
    expect(fakeApi.getDashboard).toHaveBeenCalledTimes(1);

    rerender({ rootTab: TAB_OVERVIEW, selectedProject: 'p1', selectedSource: 'local' });
    // Give any errant refetch a chance to fire, then assert it didn't.
    await new Promise((r) => setTimeout(r, 50));
    expect(fakeApi.getDashboard).toHaveBeenCalledTimes(1);
  });

  it('DOES refetch when the project query was marked stale (refetchType:"none" invalidation, e.g. after a dismiss)', async () => {
    const client = makeClient();
    const fakeApi = makeFakeApi();
    const { result, rerender } = renderCombined(client, fakeApi, {
      rootTab: 'violations', selectedProject: 'p1', selectedSource: 'local',
    });
    await waitFor(() => expect(result.current.dashboard).not.toBeNull());
    expect(fakeApi.getDashboard).toHaveBeenCalledTimes(1);

    await act(async () => {
      await client.invalidateQueries({ queryKey: projectKeys.project('p1', 'local'), refetchType: 'none' });
    });

    rerender({ rootTab: TAB_OVERVIEW, selectedProject: 'p1', selectedSource: 'local' });

    await waitFor(() => expect(fakeApi.getDashboard).toHaveBeenCalledTimes(2));
  });
});
