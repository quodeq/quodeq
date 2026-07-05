import { renderHook, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { usePrefetchRun, PREFETCH_DWELL_MS } from './usePrefetchRun.js';
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
    vi.useFakeTimers();
    vi.clearAllMocks();
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    getDashboard = vi.fn().mockResolvedValue({ dimensions: [] });
    useApi.mockReturnValue({ getDashboard });
    getProjectScores.mockResolvedValue({ trend: [] });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('warms the dashboard and scores cache after the dwell delay', async () => {
    const { result } = renderHook(() => usePrefetchRun('p1'), { wrapper: makeWrapper(queryClient) });
    result.current.prefetchRun('r1');

    await vi.advanceTimersByTimeAsync(PREFETCH_DWELL_MS);
    vi.useRealTimers();

    await waitFor(() => {
      expect(queryClient.getQueryData(projectKeys.dashboard('p1', 'r1'))).toBeTruthy();
      expect(queryClient.getQueryData(projectKeys.scores('p1', 'r1'))).toBeTruthy();
    });
    expect(getDashboard).toHaveBeenCalledWith('p1', 'r1');
    expect(getProjectScores).toHaveBeenCalledWith('p1', 'r1');
  });

  it('does not prefetch a row the pointer merely crosses', async () => {
    const { result } = renderHook(() => usePrefetchRun('p1'), { wrapper: makeWrapper(queryClient) });
    result.current.prefetchRun('r1');

    await vi.advanceTimersByTimeAsync(PREFETCH_DWELL_MS - 1);
    expect(getDashboard).not.toHaveBeenCalled();
    expect(getProjectScores).not.toHaveBeenCalled();
  });

  it('a sweep across rows fires only the last row dwelled on', async () => {
    // Regression: History rows prefetch on mouseenter. Sweeping the pointer
    // across N rows used to fire 2N requests (~4s of backend CPU per row),
    // queueing the actual click's fetches behind tens of seconds of work.
    const { result } = renderHook(() => usePrefetchRun('p1'), { wrapper: makeWrapper(queryClient) });
    result.current.prefetchRun('r1');
    await vi.advanceTimersByTimeAsync(80);
    result.current.prefetchRun('r2');
    await vi.advanceTimersByTimeAsync(80);
    result.current.prefetchRun('r3');
    await vi.advanceTimersByTimeAsync(PREFETCH_DWELL_MS);

    expect(getDashboard).toHaveBeenCalledTimes(1);
    expect(getDashboard).toHaveBeenCalledWith('p1', 'r3');
    expect(getProjectScores).toHaveBeenCalledTimes(1);
    expect(getProjectScores).toHaveBeenCalledWith('p1', 'r3');
  });

  it('cancelPrefetch drops a pending prefetch when the pointer leaves', async () => {
    const { result } = renderHook(() => usePrefetchRun('p1'), { wrapper: makeWrapper(queryClient) });
    result.current.prefetchRun('r1');
    result.current.cancelPrefetch();

    await vi.advanceTimersByTimeAsync(PREFETCH_DWELL_MS * 4);
    expect(getDashboard).not.toHaveBeenCalled();
    expect(getProjectScores).not.toHaveBeenCalled();
  });

  it('unmount clears a pending dwell timer', async () => {
    const { result, unmount } = renderHook(() => usePrefetchRun('p1'), { wrapper: makeWrapper(queryClient) });
    result.current.prefetchRun('r1');
    unmount();

    await vi.advanceTimersByTimeAsync(PREFETCH_DWELL_MS * 4);
    expect(getDashboard).not.toHaveBeenCalled();
    expect(getProjectScores).not.toHaveBeenCalled();
  });

  it('maps the latest run to the null asOf scores key', async () => {
    const { result } = renderHook(() => usePrefetchRun('p1'), { wrapper: makeWrapper(queryClient) });
    result.current.prefetchRun('latest');

    await vi.advanceTimersByTimeAsync(PREFETCH_DWELL_MS);
    vi.useRealTimers();

    await waitFor(() => {
      expect(queryClient.getQueryData(projectKeys.scores('p1', null))).toBeTruthy();
    });
    expect(getProjectScores).toHaveBeenCalledWith('p1', null);
  });

  it('does nothing without a project or run id', async () => {
    const { result } = renderHook(() => usePrefetchRun(null), { wrapper: makeWrapper(queryClient) });
    result.current.prefetchRun('r1');

    const { result: withProject } = renderHook(() => usePrefetchRun('p1'), { wrapper: makeWrapper(queryClient) });
    withProject.current.prefetchRun(null);

    await vi.advanceTimersByTimeAsync(PREFETCH_DWELL_MS * 4);
    expect(getDashboard).not.toHaveBeenCalled();
    expect(getProjectScores).not.toHaveBeenCalled();
  });
});
