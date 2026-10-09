import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useAppState } from './useAppState.js';
import { EvaluationLiveProvider } from '../features/evaluation/EvaluationLiveContext.jsx';
import { ApiProvider } from '../api/ApiContext.jsx';
import { SidePaneProvider } from '../features/side-pane/SidePaneProvider.jsx';

// Split from useAppState.test.jsx: useAppState's eval-completion single-
// refetch path, the projects-load re-arm-on-reconnect behavior, and the
// pending flag reaching the app state.

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
vi.mock('../features/evaluation/hooks/useEvaluation.js', async () => {
  const actual = await vi.importActual('../features/evaluation/hooks/useEvaluation.js');
  return {
    ...actual,
    useEvaluation: () => evaluationState,
  };
});
// Mutable so the reconnect re-arm regression below can flip connectivity;
// defaults to connected for every other test.
const healthState = { connected: true };
vi.mock('./useServerHealth.js', () => ({
  useServerHealth: () => [healthState.connected, vi.fn(), null],
}));

// Mirrors App.jsx: the root holds the state, the provider below it owns the
// evaluation lifecycle. The completion effects live in the provider, so a
// bare renderHook(useAppState) would never run them.
const capturedState = { current: null };

function AppStateHarness() {
  const state = useAppState();
  capturedState.current = state;
  return (
    <EvaluationLiveProvider store={state.liveEvaluation} {...state.evaluationDeps}>
      <span />
    </EvaluationLiveProvider>
  );
}

function renderAppState(fakeApi, client) {
  // A fresh element per render: passing the same element object back to
  // rerender lets React bail out of the subtree, so the mocked job change
  // would never reach the hook.
  const tree = () => (
    <QueryClientProvider client={client}>
      <ApiProvider value={fakeApi}>
        <SidePaneProvider><AppStateHarness /></SidePaneProvider>
      </ApiProvider>
    </QueryClientProvider>
  );
  const utils = render(tree());
  return { result: capturedState, rerender: () => utils.rerender(tree()) };
}

function makeTestClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
}

// Single refetch path on run completion. Before this task, useAppState
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
    const { result, rerender } = renderAppState(fakeApi, makeTestClient());

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
    const { result, rerender } = renderAppState(fakeApi, makeTestClient());

    await waitFor(() => expect(result.current.selectedProject).toBe('project-a'));
    const listCallsBefore = fakeApi.listProjects.mock.calls.length;

    evaluationState.job = { jobId: 'j1', status: 'done', outputProject: 'project-a', outputRunId: 'run-2' };
    rerender();

    await waitFor(() => expect(result.current.selectedRun).toBe('run-2'));
    await waitFor(() => expect(fakeApi.listProjects.mock.calls.length).toBeGreaterThan(listCallsBefore));
  });

  // The single refetch path above only proved the DASHBOARD key
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
          ? { accumulated: { score: 95 }, trend: [], availableRuns: [{ runId: backend.newRun, dateLabel: '2026-07-01', status: 'done' }] }
          : { accumulated: { score: 70 }, trend: [], availableRuns: [] }
      )),
      sharedGetProjectScores: vi.fn(),
      sharedGetProjectInfo: vi.fn(),
      backend,
    };
  }

  it('refetches scores on completion -- accumulated and availableRuns pick up the new run without a tab round-trip', async () => {
    const fakeApi = makeRunAwareFakeApi();
    const { result, rerender } = renderAppState(fakeApi, makeTestClient());

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
    const { result, rerender } = renderAppState(fakeApi, makeTestClient());

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

// The boot loader reads `pending` off the app state; useAppState picks the
// dashboard fields by name, so a field the hook returns can still be lost
// on the way up. A pending Overview must reach the gate as pending.
describe('useAppState with a pending Overview', () => {
  beforeEach(() => {
    localStorage.setItem('quodeq_selected_project', 'project-a');
    localStorage.setItem('quodeq_selected_source', 'local');
  });
  afterEach(() => {
    localStorage.removeItem('quodeq_selected_project');
    localStorage.removeItem('quodeq_selected_source');
  });

  it('exposes pending while the server is still warming the selected project', async () => {
    const fakeApi = makeAppStateFakeApi();
    fakeApi.getDashboard = vi.fn(async () => ({ pending: true, warmup: { active: true } }));
    const { result } = renderAppState(fakeApi, makeTestClient());

    await waitFor(() => expect(fakeApi.getDashboard).toHaveBeenCalled());
    await waitFor(() => expect(result.current.pending).toBe(true));
    expect(result.current.loading).toBe(true);
  });
});

// Same by-name pick: the scoring flags the dashboard hook derives only reach
// the Overview if useAppState returns them.
describe('useAppState with scoring flags from the scores payload', () => {
  beforeEach(() => {
    localStorage.setItem('quodeq_selected_project', 'project-a');
    localStorage.setItem('quodeq_selected_source', 'local');
  });
  afterEach(() => {
    localStorage.removeItem('quodeq_selected_project');
    localStorage.removeItem('quodeq_selected_source');
  });

  it('exposes customFormula and formulaUpdated', async () => {
    const fakeApi = makeAppStateFakeApi();
    fakeApi.getDashboard = vi.fn(async (project, run) => ({
      project, run: run || 'latest', trend: [], summary: { score: 75 }, dimensions: [],
      selectedRun: { runId: run || 'latest', dateLabel: '2026-05-01', gradeAlgoVersion: 3, gradesAlgoVersion: 4 },
    }));
    fakeApi.getProjectScores = vi.fn(async () => ({
      accumulated: { score: 90 }, trend: [], availableRuns: [],
      scoring: { customFormula: true, formulaVersion: 4 },
    }));
    const { result } = renderAppState(fakeApi, makeTestClient());

    await waitFor(() => expect(result.current.customFormula).toBe(true));
    await waitFor(() => expect(result.current.formulaUpdated).toBe(true));
  });
});
