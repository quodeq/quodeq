import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useSharedProjects } from './useSharedProjects.js';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { sharedKeys } from '../../../api/queryKeys.js';
import catalog from '../../../strings/en.json' with { type: 'json' };

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


// Split from useSharedProjects.test.jsx: status-error recovery,
// lastSynced fallback, ghost-cache gating, pull(), and the connect/
// refresh/pull double-submit and coalescing guards.

describe('useSharedProjects', () => {
  // A one-shot mount fetch with no retry used to leave
  // configured=false forever on any transient failure, with the ⟳ control
  // hidden (no error was ever exposed). react-query's own queries expose
  // the failure as `error`; refresh() -- the same function behind the
  // toolbar's "sync failed · retry" button -- now genuinely re-checks
  // status too, not just the list, so the retry control actually heals a
  // status-level failure instead of being a no-op forever.
  it('exposes a status-load failure as `error`, and a manual refresh() recovers it', async () => {
    const getSharedStatus = vi.fn()
      .mockRejectedValueOnce(new Error('network unreachable'))
      .mockResolvedValue({ configured: true, url: 'https://github.com/team/results.git' });
    const fakeApi = makeFakeApi({ getSharedStatus });
    const { result } = renderHook(() => useSharedProjects(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('network unreachable');
    expect(result.current.configured).toBe(false);

    await act(async () => {
      await result.current.refresh();
    });

    await waitFor(() => expect(result.current.error).toBeNull());
    await waitFor(() => expect(result.current.configured).toBe(true));
    await waitFor(() => expect(result.current.projects).toHaveLength(1));
  });

  // /status carries lastSynced on every response; a list that
  // never lands (fails on its very first fetch) must not regress the
  // toolbar to "not synced yet" when the server just reported a real sync
  // time moments ago.
  it('lastSynced comes from the status payload even when the list has never succeeded', async () => {
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({
        configured: true,
        url: 'https://github.com/team/results.git',
        lastSynced: '2026-07-15T00:00:00Z',
      })),
      sharedListProjects: vi.fn(async () => { throw new Error('list failed'); }),
    });
    const { result } = renderHook(() => useSharedProjects(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.lastSynced).toBe('2026-07-15T00:00:00Z');
    expect(result.current.error).toBe('list failed');
  });

  // Ghost shared cards after disconnect: the list query is disabled once
  // `configured` flips false, but a disabled query's cached data is not
  // cleared by invalidation alone -- it
  // just sits there. Before the fix, `projects` read straight off
  // `listQuery.data` ungated, so a lingering cache entry (left over from
  // before a disconnect, or from a DIFFERENT shared repo before a reconnect)
  // kept rendering shared cards with live pull buttons even though
  // `configured` is false. Gate on `configured` so a stale cache can never
  // surface regardless of how/when it was populated.
  it('never returns projects from a lingering list cache when unconfigured', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } } });
    // Seed the cache as if a previous, now-stale mount had already listed a
    // (possibly different) shared repo's projects.
    client.setQueryData(sharedKeys.list(), {
      projects: [{ id: 'ghost', name: 'stale-repo-entry' }],
      lastSynced: '2026-07-16T00:00:00Z',
      stale: false,
    });
    const fakeApi = makeFakeApi({ getSharedStatus: vi.fn(async () => ({ configured: false, url: null })) });
    const { result } = renderHook(() => useSharedProjects(), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={client}>
          <ApiProvider value={fakeApi}>{children}</ApiProvider>
        </QueryClientProvider>
      ),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.configured).toBe(false);
    expect(result.current.projects).toEqual([]);
  });

  it('pull(id, action) starts the job through startPull', async () => {
    const fakeApi = makeFakeApi();
    const { result } = renderHook(() => useSharedProjects(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.pull('p1', 'copy');
    });

    expect(fakeApi.startPull).toHaveBeenCalledWith('p1', 'copy');
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

  it('exposes the connect slot error, mapped by its code, while the connect job is in error', async () => {
    const failed = { configured: false, url: null, connect: { state: 'error', phase: 'error', code: 'FOREIGN_REPO', error: 'raw backend sentence' } };
    const fakeApi = makeFakeApi({ getSharedStatus: vi.fn(async () => failed) });
    const { result } = renderHook(() => useSharedProjects(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });

    await waitFor(() => expect(result.current.connectError).toBe(catalog['apiError.foreignRepo']));
  });

  it('connecting follows the connect slot while its job is active', async () => {
    const running = { configured: false, url: null, connect: { state: 'running', phase: 'downloading' } };
    const fakeApi = makeFakeApi({ getSharedStatus: vi.fn(async () => running) });
    const { result } = renderHook(() => useSharedProjects(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });

    await waitFor(() => expect(result.current.connecting).toBe(true));
  });

  it('exposes the pull slot for usePullToLocal', async () => {
    const pull = { state: 'running', phase: 'downloading', project: 'p1' };
    const fakeApi = makeFakeApi({ getSharedStatus: vi.fn(async () => ({ configured: true, url: 'u', pull })) });
    const { result } = renderHook(() => useSharedProjects(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });

    await waitFor(() => expect(result.current.pullSlot).toMatchObject(pull));
  });

  it('pull() ignores a second call while the first pull is still in flight', async () => {
    const d = deferred();
    const fakeApi = makeFakeApi({ startPull: vi.fn(() => d.promise) });
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

    expect(fakeApi.startPull).toHaveBeenCalledTimes(1);

    d.resolve({ started: true, project: 'p1' });
    await act(async () => {
      await p1;
      await p2;
    });

    expect(fakeApi.startPull).toHaveBeenCalledTimes(1);
  });
});
