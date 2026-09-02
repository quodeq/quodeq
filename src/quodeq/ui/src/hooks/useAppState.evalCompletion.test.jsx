import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useAppState } from './useAppState.js';
import { ApiProvider } from '../api/ApiContext.jsx';
import { SidePaneProvider } from '../features/side-pane/SidePaneProvider.jsx';

// Split from useAppState.test.jsx: useAppState's eval-completion single-
// refetch path (P5-T1) and the projects-load re-arm-on-reconnect behavior.

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
