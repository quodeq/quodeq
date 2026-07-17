import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import React from 'react';
import { useSharedProjects } from './useSharedProjects.js';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';

function makeFakeApi(overrides = {}) {
  return {
    getSharedStatus: vi.fn(async () => ({ configured: true, url: 'https://github.com/team/results.git' })),
    sharedListProjects: vi.fn(async () => ({
      projects: [{ id: 'p1', name: 'demo' }],
      lastSynced: '2026-07-16T00:00:00Z',
      stale: false,
    })),
    connectShared: vi.fn(async (url) => ({ configured: true, url })),
    refreshShared: vi.fn(async () => ({ stale: false, lastSynced: '2026-07-17T00:00:00Z' })),
    pullSharedProject: vi.fn(async (id) => ({ imported: true, projectId: id })),
    ...overrides,
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

describe('useSharedProjects', () => {
  it('loads status then lists projects with refresh=1 on mount (refresh-on-entry)', async () => {
    const fakeApi = makeFakeApi();
    const { result } = renderHook(() => useSharedProjects(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(fakeApi.getSharedStatus).toHaveBeenCalledTimes(1);
    expect(fakeApi.sharedListProjects).toHaveBeenCalledWith({ refresh: true });
    expect(result.current.configured).toBe(true);
    expect(result.current.url).toBe('https://github.com/team/results.git');
    expect(result.current.projects).toHaveLength(1);
    expect(result.current.lastSynced).toBe('2026-07-16T00:00:00Z');
    expect(result.current.stale).toBe(false);
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

  it('connect(url) calls connectShared then reloads status and lists projects', async () => {
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
    expect(result.current.configured).toBe(true);
    expect(result.current.projects).toHaveLength(1);
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

  it('refresh() calls refreshShared then re-lists without forcing another refresh fetch', async () => {
    const fakeApi = makeFakeApi();
    const { result } = renderHook(() => useSharedProjects(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(fakeApi.sharedListProjects).toHaveBeenCalledTimes(1);

    await act(async () => {
      await result.current.refresh();
    });

    expect(fakeApi.refreshShared).toHaveBeenCalledTimes(1);
    expect(fakeApi.sharedListProjects).toHaveBeenCalledTimes(2);
    expect(fakeApi.sharedListProjects).toHaveBeenLastCalledWith({ refresh: false });
    expect(result.current.stale).toBe(false);
  });

  // Error -> stale handling: a failed refresh must not blank out the
  // existing listing -- it flags `stale` so the page can show the
  // "refresh failed, showing results synced <time> ago" banner over the
  // still-valid last-known data.
  it('refresh() sets stale to true when refreshShared throws, keeping the existing projects/lastSynced', async () => {
    const fakeApi = makeFakeApi({
      refreshShared: vi.fn(async () => { throw new Error('network unreachable'); }),
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

  it('refresh() sets stale to true when the re-list after a successful refreshShared throws', async () => {
    const fakeApi = makeFakeApi();
    const { result } = renderHook(() => useSharedProjects(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });
    await waitFor(() => expect(result.current.loading).toBe(false));

    fakeApi.sharedListProjects.mockRejectedValueOnce(new Error('boom'));

    await act(async () => {
      await result.current.refresh();
    });

    expect(fakeApi.refreshShared).toHaveBeenCalledTimes(1);
    expect(result.current.stale).toBe(true);
  });

  it('pull(id, action) delegates to pullSharedProject', async () => {
    const fakeApi = makeFakeApi();
    const { result } = renderHook(() => useSharedProjects(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.pull('p1', 'copy');
    });

    expect(fakeApi.pullSharedProject).toHaveBeenCalledWith('p1', 'copy');
  });
});
