import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { useSharedProjects } from './useSharedProjects.js';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';

function makeFakeApi(overrides = {}) {
  const api = {
    getSharedStatus: vi.fn(async () => ({ configured: true, url: 'https://github.com/team/results.git' })),
    sharedListProjects: vi.fn(async () => ({
      projects: [{ id: 'p1', name: 'demo' }],
      lastSynced: '2026-07-16T00:00:00Z',
      stale: false,
    })),
    connectShared: vi.fn(async (url) => ({ configured: true, url })),
    startRefresh: vi.fn(async () => ({ started: true })),
    startPull: vi.fn(async (id) => ({ started: true, project: id })),
    ...overrides,
  };
  // The status poll reads getSyncStatus; these tests drive it through getSharedStatus.
  return { getSyncStatus: (...a) => api.getSharedStatus(...a), ...api };
}

function wrap(fakeApi, children) {
  const QC = withQueryClient();
  return (
    <QC>
      <ApiProvider value={fakeApi}>{children}</ApiProvider>
    </QC>
  );
}


// Split from useSharedProjects.test.jsx: mount cache/background
// revalidate, configured gating, connect(), and refresh() stale handling.

describe('useSharedProjects', () => {
  it('lists from cache on mount and never starts a remote refresh on its own', async () => {
    const fakeApi = makeFakeApi();
    const { result } = renderHook(() => useSharedProjects(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    // First render comes from cache — regression lock for the blocking-load bug.
    expect(fakeApi.sharedListProjects).toHaveBeenCalledWith({ refresh: false });
    expect(fakeApi.sharedListProjects).not.toHaveBeenCalledWith({ refresh: true });

    // The once-per-mount background refresh is gone: only refresh() starts one.
    await act(async () => {});
    expect(fakeApi.startRefresh).not.toHaveBeenCalled();
    expect(fakeApi.sharedListProjects).toHaveBeenCalledTimes(1);
  });

  it('does not start a refresh when no shared repo is configured', async () => {
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: false, url: null })),
    });
    const { result } = renderHook(() => useSharedProjects(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(fakeApi.sharedListProjects).not.toHaveBeenCalled();
    expect(fakeApi.startRefresh).not.toHaveBeenCalled();
  });

  it('does not list projects when unconfigured', async () => {
    const fakeApi = makeFakeApi({ getSharedStatus: vi.fn(async () => ({ configured: false, url: null })) });
    const { result } = renderHook(() => useSharedProjects(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.configured).toBe(false);
    expect(fakeApi.sharedListProjects).not.toHaveBeenCalled();
    expect(result.current.projects).toEqual([]);
  });

  it('connect(url) starts the job, re-reads the status and then lists projects', async () => {
    const fakeApi = makeFakeApi({ getSharedStatus: vi.fn(async () => ({ configured: false, url: null })) });
    const { result } = renderHook(() => useSharedProjects(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.configured).toBe(false);

    // After connecting, status flips to configured.
    fakeApi.getSharedStatus.mockResolvedValue({ configured: true, url: 'https://github.com/team/results.git' });

    await act(async () => {
      await result.current.connect('https://github.com/team/results.git');
    });

    expect(fakeApi.connectShared).toHaveBeenCalledWith('https://github.com/team/results.git');
    await waitFor(() => expect(result.current.configured).toBe(true));
    // The list query only becomes enabled once `configured` flips true (a
    // render after connect()'s own status invalidation resolves), so its
    // own fetch settles slightly after connect()'s returned promise does.
    await waitFor(() => expect(result.current.projects).toHaveLength(1));
  });

  it('connect(url) surfaces the API error message on failure without touching configured state', async () => {
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: false, url: null })),
      connectShared: vi.fn(async () => { throw new Error('not a valid git repository'); }),
    });
    const { result } = renderHook(() => useSharedProjects(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.connect('not-a-url');
    });

    expect(result.current.connectError).toBe('not a valid git repository');
    expect(result.current.configured).toBe(false);
  });

  it('refresh() only starts the job and re-reads the status; the list is not re-listed by it', async () => {
    const fakeApi = makeFakeApi();
    const { result } = renderHook(() => useSharedProjects(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });
    await waitFor(() => expect(result.current.loading).toBe(false));
    fakeApi.getSharedStatus.mockClear();
    fakeApi.sharedListProjects.mockClear();

    await act(async () => {
      await result.current.refresh();
    });

    expect(fakeApi.startRefresh).toHaveBeenCalledTimes(1);
    expect(fakeApi.getSharedStatus).toHaveBeenCalledTimes(1);
    expect(fakeApi.sharedListProjects).not.toHaveBeenCalled();
    expect(result.current.stale).toBe(false);
  });

  it('refreshing follows the refresh slot while its job is active', async () => {
    const running = { configured: true, url: 'u', refresh: { state: 'running', phase: 'downloading' } };
    const fakeApi = makeFakeApi({ getSharedStatus: vi.fn(async () => running) });
    const { result } = renderHook(() => useSharedProjects(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });

    await waitFor(() => expect(result.current.refreshing).toBe(true));
  });

  // Error -> stale handling: a failed refresh must not blank out the
  // existing listing -- it flags `stale` so the page can show the
  // "refresh failed, showing results synced <time> ago" banner over the
  // still-valid last-known data.
  it('refresh() sets stale to true when startRefresh throws, keeping the existing projects/lastSynced', async () => {
    const fakeApi = makeFakeApi({
      startRefresh: vi.fn(async () => { throw new Error('network unreachable'); }),
    });
    const { result } = renderHook(() => useSharedProjects(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });
    await waitFor(() => expect(result.current.loading).toBe(false));
    const priorProjects = result.current.projects;
    const priorLastSynced = result.current.lastSynced;

    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.stale).toBe(true);
    expect(result.current.projects).toBe(priorProjects);
    expect(result.current.lastSynced).toBe(priorLastSynced);
  });

  it('stale is true while the last refresh job ended in error, keeping the projects on screen', async () => {
    const failed = { configured: true, url: 'u', refresh: { state: 'error', phase: 'error', code: 'GIT_FAILED' } };
    const fakeApi = makeFakeApi({ getSharedStatus: vi.fn(async () => failed) });
    const { result } = renderHook(() => useSharedProjects(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });

    await waitFor(() => expect(result.current.stale).toBe(true));
    await waitFor(() => expect(result.current.projects).toHaveLength(1));
  });
});
