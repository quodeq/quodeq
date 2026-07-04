import { renderHook, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { usePrefetchRun } from './usePrefetchRun.js';
import { useApi } from '../../../api/ApiContext.jsx';
import { getProjectScores } from '../../../api/index.js';
import { projectKeys } from '../../../api/queryKeys.js';

vi.mock('../../../api/ApiContext.jsx', () => ({
  useApi: vi.fn(),
}));
vi.mock('../../../api/index.js', () => ({
  getProjectScores: vi.fn(),
}));

function makeWrapper(queryClient) {
  return function Wrapper({ children }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe('usePrefetchRun', () => {
  let queryClient;
  let getDashboard;

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    getDashboard = vi.fn().mockResolvedValue({ dimensions: [] });
    useApi.mockReturnValue({ getDashboard });
    getProjectScores.mockResolvedValue({ trend: [] });
  });

  it('warms the dashboard and scores cache for a run', async () => {
    const { result } = renderHook(() => usePrefetchRun('p1'), { wrapper: makeWrapper(queryClient) });
    result.current('r1');

    await waitFor(() => {
      expect(queryClient.getQueryData(projectKeys.dashboard('p1', 'r1'))).toBeTruthy();
      expect(queryClient.getQueryData(projectKeys.scores('p1', 'r1'))).toBeTruthy();
    });
    expect(getDashboard).toHaveBeenCalledWith('p1', 'r1');
    expect(getProjectScores).toHaveBeenCalledWith('p1', 'r1');
  });

  it('maps the latest run to the null asOf scores key', async () => {
    const { result } = renderHook(() => usePrefetchRun('p1'), { wrapper: makeWrapper(queryClient) });
    result.current('latest');

    await waitFor(() => {
      expect(queryClient.getQueryData(projectKeys.scores('p1', null))).toBeTruthy();
    });
    expect(getProjectScores).toHaveBeenCalledWith('p1', null);
  });

  it('does nothing without a project or run id', () => {
    const { result } = renderHook(() => usePrefetchRun(null), { wrapper: makeWrapper(queryClient) });
    result.current('r1');

    const { result: withProject } = renderHook(() => usePrefetchRun('p1'), { wrapper: makeWrapper(queryClient) });
    withProject.current(null);

    expect(getDashboard).not.toHaveBeenCalled();
    expect(getProjectScores).not.toHaveBeenCalled();
  });
});
