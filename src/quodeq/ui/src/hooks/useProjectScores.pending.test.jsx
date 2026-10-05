import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useProjectScores } from './useProjectScores';
import { withQueryClient } from '../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../api/ApiContext.jsx';

// A pending body (the server's warm-up still owes the project) is loading,
// not scores: nothing downstream may read it as a project with no runs.
const PENDING = { pending: true, warmup: { active: true, projectsDone: 0, projectsTotal: 1, currentProjectName: 'p1' } };

function wrap(fakeApi, children) {
  const QC = withQueryClient();
  return (
    <QC>
      <ApiProvider value={fakeApi}>{children}</ApiProvider>
    </QC>
  );
}

describe('useProjectScores with a pending payload', () => {
  it('keeps scores null, loading true and the run list empty', async () => {
    const fakeApi = { getProjectScores: vi.fn(async () => PENDING), sharedGetProjectScores: vi.fn() };
    const { result } = renderHook(
      () => useProjectScores({ selectedProject: 'p1', selectedRun: null }),
      { wrapper: ({ children }) => wrap(fakeApi, children) },
    );
    await waitFor(() => expect(fakeApi.getProjectScores).toHaveBeenCalled());
    await waitFor(() => expect(result.current.loading).toBe(true));
    expect(result.current.scores).toBeNull();
    expect(result.current.latestScores).toBeNull();
    expect(result.current.availableRuns).toEqual([]);
    expect(result.current.error).toBeNull();
  });
});
