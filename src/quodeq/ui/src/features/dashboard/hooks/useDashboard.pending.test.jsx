import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useDashboard } from './useDashboard';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';

// While the server's warm-up still owes the project, the Overview routes
// answer a pending body. The hook must read that as "still loading", never
// as an empty project or an error, and say it is pending so the boot loader
// drops into the Overview's own loading state while the query polls.
const PENDING = { pending: true, warmup: { active: true, projectsDone: 0, projectsTotal: 2, currentProjectName: 'quodeq' } };

function makeFakeApi({ dashboard = PENDING, scores = { accumulated: { score: 90 }, trend: [], availableRuns: [] } } = {}) {
  return {
    getDashboard: vi.fn(async () => dashboard),
    sharedGetDashboard: vi.fn(async () => dashboard),
    getProjectScores: vi.fn(async () => scores),
    sharedGetProjectScores: vi.fn(async () => scores),
    sharedGetProjectInfo: vi.fn(async () => null),
  };
}

function wrap(fakeApi, children) {
  const QC = withQueryClient();
  return (
    <QC>
      <ApiProvider value={fakeApi}>{children}</ApiProvider>
    </QC>
  );
}

describe('useDashboard with a pending Overview', () => {
  it('reports loading and no dashboard while the dashboard payload is pending', async () => {
    const fakeApi = makeFakeApi();
    const { result } = renderHook(
      () => useDashboard({ selectedProject: 'p1', selectedRun: null }),
      { wrapper: ({ children }) => wrap(fakeApi, children) },
    );
    await waitFor(() => expect(fakeApi.getDashboard).toHaveBeenCalled());
    await waitFor(() => expect(result.current.accumulated?.score).toBe(90));
    expect(result.current.dashboard).toBeNull();
    expect(result.current.loading).toBe(true);
    expect(result.current.pending).toBe(true);
    expect(result.current.error).toBeNull();
  });

  it('reports loading and no accumulated scores while the scores payload is pending', async () => {
    const fakeApi = makeFakeApi({
      dashboard: { project: 'p1', trend: [], summary: {}, dimensions: [], selectedRun: { runId: 'r1' } },
      scores: PENDING,
    });
    const { result } = renderHook(
      () => useDashboard({ selectedProject: 'p1', selectedRun: null }),
      { wrapper: ({ children }) => wrap(fakeApi, children) },
    );
    await waitFor(() => expect(result.current.dashboard?.selectedRun?.runId).toBe('r1'));
    await waitFor(() => expect(fakeApi.getProjectScores).toHaveBeenCalled());
    expect(result.current.accumulated).toBeNull();
    expect(result.current.loading).toBe(true);
    expect(result.current.pending).toBe(true);
    expect(result.current.error).toBeNull();
  });
});

describe('useDashboard with a last known grade in the pending body', () => {
  it('exposes lastKnown while pending and drops it once the payload lands', async () => {
    const lastKnown = { grade: 'B', score: 7.4, files: 12 };
    const fakeApi = makeFakeApi({ dashboard: { ...PENDING, lastKnown } });
    const { result } = renderHook(
      () => useDashboard({ selectedProject: 'p1', selectedRun: null }),
      { wrapper: ({ children }) => wrap(fakeApi, children) },
    );
    await waitFor(() => expect(result.current.pending).toBe(true));
    expect(result.current.lastKnown).toEqual(lastKnown);

    fakeApi.getDashboard.mockResolvedValue({ project: 'p1', trend: [], summary: {}, dimensions: [], selectedRun: { runId: 'r1' } });
    await waitFor(() => expect(result.current.dashboard?.selectedRun?.runId).toBe('r1'), { timeout: 5000 });
    expect(result.current.lastKnown).toBeNull();
  });

  it('is null when the pending body carries no summary', async () => {
    const fakeApi = makeFakeApi();
    const { result } = renderHook(
      () => useDashboard({ selectedProject: 'p1', selectedRun: null }),
      { wrapper: ({ children }) => wrap(fakeApi, children) },
    );
    await waitFor(() => expect(result.current.pending).toBe(true));
    expect(result.current.lastKnown).toBeNull();
  });
});

