import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useAppState, useOverviewReturnReconcile, TAB_OVERVIEW, KNOWN_TABS } from './useAppState.js';
import { useNavStack } from './useNavStack.js';
import { useDashboard } from '../features/dashboard/hooks/useDashboard.js';
import { ApiProvider } from '../api/ApiContext.jsx';
import { SidePaneProvider } from '../features/side-pane/SidePaneProvider.jsx';
import { projectKeys } from '../api/queryKeys.js';

// useAppState composes useEvaluationLifecycle (-> useEvaluation) and
// useServerHealth. Mocked the same way useEvaluationLifecycle.test.jsx mocks
// useEvaluation, so the eval-completion regression below can drive `job`
// directly without a real evaluation API, and without useServerHealth's
// real network polling.
const evaluationState = {
  job: null, jobError: null, liveViolations: {},
  startEvaluation: vi.fn(), clearJob: vi.fn(), cancelEvaluation: vi.fn(),
  startedProject: null,
};
vi.mock('../features/evaluation/hooks/useEvaluation.js', () => ({
  useEvaluation: () => evaluationState,
  LOCAL_API_PROVIDERS: new Set(['ollama', 'llamacpp', 'omlx']),
}));
// Mutable so the reconnect re-arm regression below can flip connectivity;
// defaults to connected for every other test.
const healthState = { connected: true };
vi.mock('./useServerHealth.js', () => ({
  useServerHealth: () => [healthState.connected, vi.fn(), null],
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

  // Documents WHY rootTab (not activeTab) is required: useAppState.js's
  // activeTab fallback formula, replayed here verbatim against the exact
  // untagged 'evalprinciple' page ExplorerPage.onPrincipleClick pushes,
  // resolves to TAB_OVERVIEW -- the misclassification the reviewer flagged.
  it('the legacy activeTab-fallback formula misclassifies the same untagged page as overview', () => {
    const activePage = { page: 'evalprinciple', evalPrincipal: { principle: 'P' } };
    const legacyActiveTab = KNOWN_TABS.includes(activePage.page) ? activePage.page
      : activePage.sourceTab && KNOWN_TABS.includes(activePage.sourceTab) ? activePage.sourceTab
      : activePage.page === 'history-run' ? 'history'
      : TAB_OVERVIEW;
    expect(legacyActiveTab).toBe(TAB_OVERVIEW);
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

// P5-T1: single refetch path on run completion. Before this task, useAppState
// ran its OWN eval-completion effect (refreshDashboardActive, keyed off
// job.outputRunId) in the same effect-flush as useEvaluationLifecycle's
// selectProjectAndRun. That effect fired before selectedRun's state update
// had committed, so its active invalidation hit the OLD (pre-run) dashboard
// key — a redundant refetch. useEvaluationLifecycle is now the only
// completion path: selectProjectAndRun mints the NEW query key, and that key
// change is the only refetch a completed run causes.
function makeAppStateFakeApi() {
  return {
    listProjects: vi.fn(async () => [{ id: 'project-a', name: 'Project A' }]),
    getDashboard: vi.fn(async (project, run) => ({
      project, run: run || 'latest', trend: [], summary: { score: 75 }, dimensions: [],
      selectedRun: { runId: run || 'latest', dateLabel: '2026-05-01' },
    })),
    sharedGetDashboard: vi.fn(),
    getProjectScores: vi.fn(async () => ({ accumulated: { score: 90 }, trend: [], availableRuns: [] })),
    sharedGetProjectScores: vi.fn(),
    sharedGetProjectInfo: vi.fn(),
  };
}

describe('useAppState eval-completion: single refetch path (P5-T1)', () => {
  beforeEach(() => {
    evaluationState.job = null;
    localStorage.setItem('quodeq_selected_project', 'project-a');
    localStorage.setItem('quodeq_selected_source', 'local');
  });
  afterEach(() => {
    localStorage.removeItem('quodeq_selected_project');
    localStorage.removeItem('quodeq_selected_source');
  });

  it('refetches only the new run key on completion -- no redundant active refetch of the pre-run key', async () => {
    const fakeApi = makeAppStateFakeApi();
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
    });
    const { result, rerender } = renderHook(() => useAppState(), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={client}>
          <ApiProvider value={fakeApi}>
            <SidePaneProvider>{children}</SidePaneProvider>
          </ApiProvider>
        </QueryClientProvider>
      ),
    });

    await waitFor(() => expect(result.current.selectedProject).toBe('project-a'));
    await waitFor(() => expect(fakeApi.getDashboard).toHaveBeenCalledTimes(1));
    expect(fakeApi.getDashboard).toHaveBeenNthCalledWith(1, 'project-a', 'latest');

    evaluationState.job = { jobId: 'j1', status: 'done', outputProject: 'project-a', outputRunId: 'run-2' };
    rerender();

    await waitFor(() => expect(result.current.selectedRun).toBe('run-2'));
    await waitFor(() => expect(fakeApi.getDashboard).toHaveBeenCalledTimes(2));
    expect(fakeApi.getDashboard).toHaveBeenNthCalledWith(2, 'project-a', 'run-2');
    expect(fakeApi.getDashboard.mock.calls.filter(([p, r]) => p === 'project-a' && r === 'latest')).toHaveLength(1);

    // Settle a beat longer to catch any late-firing redundant refetch.
    await new Promise((r) => setTimeout(r, 50));
    expect(fakeApi.getDashboard).toHaveBeenCalledTimes(2);
  });

  it('still refreshes the project list and moves the selection on completion (selectProjectAndRun/loadProjects remain wired)', async () => {
    const fakeApi = makeAppStateFakeApi();
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
    });
    const { result, rerender } = renderHook(() => useAppState(), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={client}>
          <ApiProvider value={fakeApi}>
            <SidePaneProvider>{children}</SidePaneProvider>
          </ApiProvider>
        </QueryClientProvider>
      ),
    });

    await waitFor(() => expect(result.current.selectedProject).toBe('project-a'));
    const listCallsBefore = fakeApi.listProjects.mock.calls.length;

    evaluationState.job = { jobId: 'j1', status: 'done', outputProject: 'project-a', outputRunId: 'run-2' };
    rerender();

    await waitFor(() => expect(result.current.selectedRun).toBe('run-2'));
    await waitFor(() => expect(fakeApi.listProjects.mock.calls.length).toBeGreaterThan(listCallsBefore));
  });

  // Finding 1 (P5 final review): P5-T1 above only proved the DASHBOARD key
  // refetches on completion. It missed that the SCORES key -- the `latest`
  // query behind `accumulated`/`availableRuns` -- has no dependency on
  // selectedRun at all, so nothing refetched it once useAppState stopped
  // calling refreshDashboardActive. This fake, unlike makeAppStateFakeApi
  // above, is run-aware: getProjectScores returns an empty availableRuns
  // (and a stale accumulated) until the fake's "backend" is told the new run
  // exists, mirroring what the real API would return once a run completes.
  function makeRunAwareFakeApi() {
    const backend = { newRun: null };
    return {
      listProjects: vi.fn(async () => [{ id: 'project-a', name: 'Project A' }]),
      getDashboard: vi.fn(async (project, run) => ({
        project, run: run || 'latest', trend: [], summary: { score: 75 }, dimensions: [],
        selectedRun: { runId: run || 'latest', dateLabel: '2026-05-01' },
      })),
      sharedGetDashboard: vi.fn(),
      getProjectScores: vi.fn(async () => (
        backend.newRun
          ? { accumulated: { score: 95 }, trend: [], availableRuns: [{ runId: backend.newRun, dateLabel: '2026-07-01', status: 'complete' }] }
          : { accumulated: { score: 70 }, trend: [], availableRuns: [] }
      )),
      sharedGetProjectScores: vi.fn(),
      sharedGetProjectInfo: vi.fn(),
      backend,
    };
  }

  it('refetches scores on completion -- accumulated and availableRuns pick up the new run without a tab round-trip', async () => {
    const fakeApi = makeRunAwareFakeApi();
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
    });
    const { result, rerender } = renderHook(() => useAppState(), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={client}>
          <ApiProvider value={fakeApi}>
            <SidePaneProvider>{children}</SidePaneProvider>
          </ApiProvider>
        </QueryClientProvider>
      ),
    });

    await waitFor(() => expect(result.current.selectedProject).toBe('project-a'));
    await waitFor(() => expect(result.current.accumulated).toEqual({ score: 70 }));
    const scoresCallsBefore = fakeApi.getProjectScores.mock.calls.length;

    // The run completes: the backend now knows about it, and the job
    // transitions to done in the same tick a real completion would.
    fakeApi.backend.newRun = 'run-2';
    evaluationState.job = { jobId: 'j1', status: 'done', outputProject: 'project-a', outputRunId: 'run-2' };
    rerender();

    await waitFor(() => expect(fakeApi.getProjectScores.mock.calls.length).toBeGreaterThan(scoresCallsBefore));
    await waitFor(() => expect(result.current.accumulated).toEqual({ score: 95 }));
    await waitFor(() => expect(result.current.availableRuns.some((r) => r.runId === 'run-2')).toBe(true));
  });
});

// v1.9.0 startup-spinner regression, third recovery lane: if the projects load
// exhausted its retries while the backend was unreachable, a later reconnect
// (health poll coming back) must re-fire the load -- otherwise the only way
// out is the manual Retry button.
describe('useAppState projects-load re-arm on server reconnect', () => {
  beforeEach(() => {
    evaluationState.job = null;
    healthState.connected = true;
    localStorage.setItem('quodeq_selected_project', 'project-a');
    localStorage.setItem('quodeq_selected_source', 'local');
  });
  afterEach(() => {
    healthState.connected = true;
    localStorage.removeItem('quodeq_selected_project');
    localStorage.removeItem('quodeq_selected_source');
  });

  it('reloads the project list when connectivity returns after the load failed', async () => {
    const fakeApi = makeAppStateFakeApi();
    fakeApi.listProjects.mockRejectedValue(new Error('backend still starting'));
    healthState.connected = false;
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
    });
    const { result, rerender } = renderHook(() => useAppState(), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={client}>
          <ApiProvider value={fakeApi}>
            <SidePaneProvider>{children}</SidePaneProvider>
          </ApiProvider>
        </QueryClientProvider>
      ),
    });

    await waitFor(() => expect(result.current.projectsLoadFailed).toBe(true), { timeout: 5000 });
    const callsWhileDown = fakeApi.listProjects.mock.calls.length;

    fakeApi.listProjects.mockResolvedValue([{ id: 'project-a', name: 'Project A' }]);
    healthState.connected = true;
    rerender();

    await waitFor(() => expect(result.current.projectsLoaded).toBe(true), { timeout: 5000 });
    expect(fakeApi.listProjects.mock.calls.length).toBeGreaterThan(callsWhileDown);
    expect(result.current.projectsLoadFailed).toBe(false);
  });
});
