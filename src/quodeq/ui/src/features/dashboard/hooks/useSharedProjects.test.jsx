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

// A promise the test controls the settlement of, so we can assert on
// behaviour while a call is genuinely still in flight (the double-submit
// window), rather than a promise that resolves on the same microtask tick.
function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
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
  it('lists from cache on mount and refreshes in the background (never blocks)', async () => {
    const fakeApi = makeFakeApi();
    const { result } = renderHook(() => useSharedProjects(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    // First render comes from cache — regression lock for the blocking-load bug.
    expect(fakeApi.sharedListProjects).toHaveBeenCalledWith({ refresh: false });
    expect(fakeApi.sharedListProjects).not.toHaveBeenCalledWith({ refresh: true });

    // Background revalidate: refreshShared fires after the cached render, then re-lists.
    await waitFor(() => expect(fakeApi.refreshShared).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(fakeApi.sharedListProjects).toHaveBeenCalledTimes(2));
  });

  it('does not fire a background refresh when no shared repo is configured', async () => {
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: false, url: null })),
    });
    const { result } = renderHook(() => useSharedProjects(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(fakeApi.sharedListProjects).not.toHaveBeenCalled();
    expect(fakeApi.refreshShared).not.toHaveBeenCalled();
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
    // Let the mount's own background revalidate settle first, then measure
    // a manual refresh() call in isolation from it.
    await waitFor(() => expect(fakeApi.sharedListProjects).toHaveBeenCalledTimes(2));
    fakeApi.refreshShared.mockClear();
    fakeApi.sharedListProjects.mockClear();

    await act(async () => {
      await result.current.refresh();
    });

    expect(fakeApi.refreshShared).toHaveBeenCalledTimes(1);
    expect(fakeApi.sharedListProjects).toHaveBeenCalledTimes(1);
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
    // Let the mount's own background revalidate settle first, so only the
    // manual refresh() call below is counted.
    await waitFor(() => expect(fakeApi.sharedListProjects).toHaveBeenCalledTimes(2));
    fakeApi.refreshShared.mockClear();

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

  // Double-submit guards: aria-disabled doesn't block a click in this
  // codebase (see ProjectsPage.jsx's is-disabled convention), so connect/
  // refresh/pull must no-op on a repeat call while the first is still in
  // flight, regardless of which UI path triggered it (click, Enter key,
  // card action).
  it('connect() ignores a second call while the first connect is still in flight', async () => {
    const d = deferred();
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: false, url: null })),
      connectShared: vi.fn(() => d.promise),
    });
    const { result } = renderHook(() => useSharedProjects(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });
    await waitFor(() => expect(result.current.loading).toBe(false));

    let p1;
    let p2;
    act(() => {
      p1 = result.current.connect('https://github.com/team/results.git');
      p2 = result.current.connect('https://github.com/team/results.git');
    });

    expect(fakeApi.connectShared).toHaveBeenCalledTimes(1);

    d.resolve({ configured: true, url: 'https://github.com/team/results.git' });
    await act(async () => {
      await p1;
      await p2;
    });

    expect(fakeApi.connectShared).toHaveBeenCalledTimes(1);
  });

  it('refresh() ignores a second call while the first refresh is still in flight', async () => {
    const d = deferred();
    const fakeApi = makeFakeApi();
    const { result } = renderHook(() => useSharedProjects(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });
    await waitFor(() => expect(result.current.loading).toBe(false));
    // Let the mount's own background revalidate settle first, so the
    // deferred stub below only governs the two manual refresh() calls,
    // not the mount's in-flight refresh.
    await waitFor(() => expect(fakeApi.sharedListProjects).toHaveBeenCalledTimes(2));
    fakeApi.refreshShared.mockClear();
    fakeApi.refreshShared.mockImplementation(() => d.promise);

    let p1;
    let p2;
    act(() => {
      p1 = result.current.refresh();
      p2 = result.current.refresh();
    });

    expect(fakeApi.refreshShared).toHaveBeenCalledTimes(1);

    d.resolve({ stale: false, lastSynced: '2026-07-17T00:00:00Z' });
    await act(async () => {
      await p1;
      await p2;
    });

    expect(fakeApi.refreshShared).toHaveBeenCalledTimes(1);
  });

  it('pull() ignores a second call while the first pull is still in flight', async () => {
    const d = deferred();
    const fakeApi = makeFakeApi({ pullSharedProject: vi.fn(() => d.promise) });
    const { result } = renderHook(() => useSharedProjects(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });
    await waitFor(() => expect(result.current.loading).toBe(false));

    let p1;
    let p2;
    act(() => {
      p1 = result.current.pull('p1');
      p2 = result.current.pull('p1');
    });

    expect(fakeApi.pullSharedProject).toHaveBeenCalledTimes(1);

    d.resolve({ imported: true, projectId: 'p1' });
    await act(async () => {
      await p1;
      await p2;
    });

    expect(fakeApi.pullSharedProject).toHaveBeenCalledTimes(1);
  });
});
