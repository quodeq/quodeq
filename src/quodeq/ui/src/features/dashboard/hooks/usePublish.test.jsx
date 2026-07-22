import { describe, it, expect, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { usePublish } from './usePublish.js';
import { useSharedProjects } from './useSharedProjects.js';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { sharedKeys } from '../../../api/queryKeys.js';

function makeFakeApi(overrides = {}) {
  return {
    getSharedStatus: vi.fn(async () => ({
      configured: true,
      url: 'https://github.com/team/results.git',
      publish: { state: 'idle', project: null, runs: null, error: null, finishedAt: null },
    })),
    sharedListProjects: vi.fn(async () => ({ projects: [], lastSynced: null, stale: false })),
    publishProject: vi.fn(async () => ({ started: true })),
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

// Rerender-safe wrapper: builds the QueryClient wrapper component ONCE.
// The inline `({ children }) => wrap(fakeApi, children)` idiom above calls
// withQueryClient() on every render, producing a NEW component type each
// time -- a rerender() would remount the whole tree and silently reset all
// hook state. Tests that rerender (the enabled-toggle repros) must use this.
function makeStableWrapper(fakeApi) {
  const QC = withQueryClient();
  return function StableWrapper({ children }) {
    return (
      <QC>
        <ApiProvider value={fakeApi}>{children}</ApiProvider>
      </QC>
    );
  };
}

describe('usePublish', () => {
  it('publish(id) ignores a second call while the first is still in flight (double-click guard)', async () => {
    const d = deferred();
    const fakeApi = makeFakeApi({ publishProject: vi.fn(() => d.promise) });
    const { result } = renderHook(() => usePublish({ enabled: false }), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });

    let p1;
    let p2;
    act(() => {
      p1 = result.current.publish('p1');
      p2 = result.current.publish('p1');
    });

    expect(fakeApi.publishProject).toHaveBeenCalledTimes(1);

    d.resolve({ started: true });
    await act(async () => {
      await p1;
      await p2;
    });

    expect(fakeApi.publishProject).toHaveBeenCalledTimes(1);
  });

  it('sets publishState to running with the publishing project id once the POST succeeds', async () => {
    const fakeApi = makeFakeApi();
    const { result } = renderHook(() => usePublish({ enabled: false }), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });

    await act(async () => {
      await result.current.publish('p1');
    });

    expect(fakeApi.publishProject).toHaveBeenCalledWith('p1');
    expect(result.current.publishState).toBe('running');
    expect(result.current.publishingProject).toBe('p1');
  });

  it('polls getSharedStatus every 2s while running and stops once done, refetching the shared list', async () => {
    vi.useFakeTimers();
    try {
      const getSharedStatus = vi.fn()
        .mockResolvedValueOnce({ configured: true, publish: { state: 'running', project: 'p1' } })
        .mockResolvedValueOnce({ configured: true, publish: { state: 'running', project: 'p1' } })
        .mockResolvedValueOnce({ configured: true, publish: { state: 'done', project: 'p1', runs: 3 } });
      const sharedListProjects = vi.fn(async () => ({
        projects: [{ id: 'p1', name: 'demo', publishedAt: '2026-07-17T00:00:00Z' }],
        lastSynced: '2026-07-17T00:00:00Z',
        stale: false,
      }));
      const fakeApi = makeFakeApi({ getSharedStatus, sharedListProjects });
      const { result } = renderHook(() => usePublish({ enabled: false }), {
        wrapper: ({ children }) => wrap(fakeApi, children),
      });

      await act(async () => {
        await result.current.publish('p1');
      });
      expect(result.current.publishState).toBe('running');
      expect(getSharedStatus).toHaveBeenCalledTimes(0); // no poll tick has fired yet

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });
      expect(getSharedStatus).toHaveBeenCalledTimes(1);
      expect(result.current.publishState).toBe('running');

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });
      expect(getSharedStatus).toHaveBeenCalledTimes(2);
      expect(result.current.publishState).toBe('running');

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });
      expect(getSharedStatus).toHaveBeenCalledTimes(3);
      expect(result.current.publishState).toBe('done');
      expect(sharedListProjects).toHaveBeenCalledWith({ refresh: false });
      expect(result.current.publishedAtByProject.p1).toBe('2026-07-17T00:00:00Z');

      // Polling must actually stop -- no further getSharedStatus calls.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(4000);
      });
      expect(getSharedStatus).toHaveBeenCalledTimes(3);
    } finally {
      vi.useRealTimers();
    }
  });

  // Minor finding (final whole-branch review): refreshListAfterCompletion's
  // fetchQuery inherited the production QueryClient's staleTime: 30s (see
  // api/queryClient.js), so it could resolve straight from a still-fresh
  // cache entry instead of actually fetching -- silently contradicting its
  // own doc comment ("always performs the fetch"). withQueryClient() (used by
  // every other test in this file) sets staleTime: 0 for the whole test
  // client, which would mask the bug -- a 0-staleTime entry is already
  // "stale" regardless of the fix, so fetchQuery would refetch either way.
  // This test builds its own client with production's real staleTime: 30_000
  // so the assertion actually exercises the bug.
  it('refetches the shared list after a completed publish even when the cached entry is still within staleTime', async () => {
    vi.useFakeTimers();
    try {
      const getSharedStatus = vi.fn(async () => ({
        configured: true,
        publish: { state: 'done', project: 'p1', runs: 2 },
      }));
      const sharedListProjects = vi.fn(async () => ({
        projects: [{ id: 'p1', name: 'demo', publishedAt: '2026-07-18T00:00:00Z' }],
        lastSynced: '2026-07-18T00:00:00Z',
        stale: false,
      }));
      const fakeApi = makeFakeApi({ getSharedStatus, sharedListProjects });

      const client = new QueryClient({
        defaultOptions: { queries: { staleTime: 30_000, gcTime: 5 * 60_000, retry: false } },
      });
      // Seed the list cache with a fresh entry (just written, well inside the
      // 30s staleTime window) -- absent the fix, fetchQuery would resolve
      // straight from this without ever calling sharedListProjects again.
      client.setQueryData(sharedKeys.list(), {
        projects: [{ id: 'p1', name: 'demo', publishedAt: '2026-07-17T00:00:00Z' }],
        lastSynced: '2026-07-17T00:00:00Z',
        stale: false,
      });

      const { result } = renderHook(() => usePublish({ enabled: false }), {
        wrapper: ({ children }) => (
          <QueryClientProvider client={client}>
            <ApiProvider value={fakeApi}>{children}</ApiProvider>
          </QueryClientProvider>
        ),
      });

      await act(async () => {
        await result.current.publish('p1');
      });
      expect(result.current.publishState).toBe('running');
      expect(sharedListProjects).not.toHaveBeenCalled();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });

      // advanceTimersByTimeAsync flushes the microtask chain triggered by the
      // tick (checkStatus -> refreshListAfterCompletion -> fetchQuery), so
      // the outcome is already settled here -- no waitFor needed (and
      // waitFor's own timer-driven polling would hang under fake timers).
      expect(result.current.publishState).toBe('done');
      // The completion refresh must hit the network for fresh data, not
      // resolve silently from the still-fresh cache entry seeded above.
      expect(sharedListProjects).toHaveBeenCalledWith({ refresh: false });
      expect(result.current.publishedAtByProject.p1).toBe('2026-07-18T00:00:00Z');
    } finally {
      vi.useRealTimers();
    }
  });

  // Audit C3/C4: the "published <relative time>" meta, the PUBLISHED badge,
  // and the publish/update button used to update at different speeds --
  // the meta from usePublish's own cheap refetch, the badge/button only once
  // the (possibly-coalesced, possibly-slow) authoritative refresh landed.
  // The fix optimistically upserts the published id into the shared list
  // cache the instant the job reports 'done', synchronously before the
  // authoritative refresh's network round trip even starts -- so every
  // consumer of sharedKeys.list() flips in the same render. This test holds
  // the authoritative refresh open to prove the cache is patched BEFORE it
  // resolves, then resolves it to prove the optimistic entry gets
  // overwritten by real server data rather than left stale.
  it('optimistically patches the list cache with the published id before the authoritative refresh resolves, then the refresh overwrites it', async () => {
    vi.useFakeTimers();
    try {
      const getSharedStatus = vi.fn(async () => ({
        configured: true,
        publish: { state: 'done', project: 'p1', runs: 1 },
      }));
      let resolveList;
      const sharedListProjects = vi.fn(() => new Promise((resolve) => { resolveList = resolve; }));
      const fakeApi = makeFakeApi({ getSharedStatus, sharedListProjects });

      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const { result } = renderHook(() => usePublish({ enabled: false }), {
        wrapper: ({ children }) => (
          <QueryClientProvider client={client}>
            <ApiProvider value={fakeApi}>{children}</ApiProvider>
          </QueryClientProvider>
        ),
      });

      const local = {
        id: 'p1',
        name: 'demo',
        latestRunId: 'run-9',
        latestDoneRunId: 'run-9',
        originUrl: 'https://github.com/org/demo',
      };
      await act(async () => {
        await result.current.publish('p1', local);
      });
      expect(result.current.publishState).toBe('running');

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });

      // The poll saw 'done' and the optimistic patch landed synchronously --
      // the authoritative refresh (sharedListProjects) is still pending
      // (resolveList captured but not yet called).
      expect(resolveList).toBeDefined();
      const midFlight = client.getQueryData(sharedKeys.list());
      const optimisticEntry = midFlight.projects.find((p) => p.id === 'p1');
      expect(optimisticEntry).toMatchObject({
        id: 'p1',
        name: 'demo',
        publishedBy: null,
        source: 'shared',
        latestRunId: 'run-9',
        latestDoneRunId: 'run-9',
        originUrl: 'https://github.com/org/demo',
      });
      expect(optimisticEntry.publishedAt).toEqual(expect.any(Number));
      expect(result.current.publishState).toBe('done');

      // Now let the authoritative refresh resolve with real server data --
      // it must overwrite the optimistic entry, not merely coexist with it.
      resolveList({
        projects: [{ id: 'p1', name: 'demo', publishedAt: '2026-07-19T00:00:00Z', publishedBy: 'alice' }],
        lastSynced: '2026-07-19T00:00:00Z',
        stale: false,
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });

      const settled = client.getQueryData(sharedKeys.list());
      const finalEntry = settled.projects.find((p) => p.id === 'p1');
      expect(finalEntry.publishedBy).toBe('alice');
      expect(finalEntry.publishedAt).toBe('2026-07-19T00:00:00Z');
    } finally {
      vi.useRealTimers();
    }
  });

  it('a 409 from the POST itself surfaces the message inline without crashing', async () => {
    const err = new Error('a publish is already running');
    const fakeApi = makeFakeApi({ publishProject: vi.fn(async () => { throw err; }) });
    const { result } = renderHook(() => usePublish({ enabled: false }), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });

    await act(async () => {
      await result.current.publish('p2');
    });

    expect(result.current.publishError).toBe('a publish is already running');
    expect(result.current.publishErrorProject).toBe('p2');
    expect(result.current.publishState).not.toBe('running');
  });

  it('a rejected POST does not clobber a genuinely running job for a different project', async () => {
    const fakeApi = makeFakeApi();
    const { result } = renderHook(() => usePublish({ enabled: false }), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });

    // p1's publish genuinely starts.
    await act(async () => {
      await result.current.publish('p1');
    });
    expect(result.current.publishState).toBe('running');
    expect(result.current.publishingProject).toBe('p1');

    // A click on p2's button while p1 is running hits the backend's single-job
    // guard and gets a 409 -- p1's still-running status must not be reset.
    fakeApi.publishProject.mockRejectedValueOnce(new Error('a publish is already running'));
    await act(async () => {
      await result.current.publish('p2');
    });

    expect(result.current.publishError).toBe('a publish is already running');
    expect(result.current.publishErrorProject).toBe('p2');
    expect(result.current.publishState).toBe('running');
    expect(result.current.publishingProject).toBe('p1');
  });

  it('does not fetch shared status/list on mount when enabled is false', async () => {
    const fakeApi = makeFakeApi();
    renderHook(() => usePublish({ enabled: false }), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });
    await act(async () => {});
    expect(fakeApi.getSharedStatus).not.toHaveBeenCalled();
  });

  it('fetches configured status and the shared list (refresh: false) on mount when enabled', async () => {
    const fakeApi = makeFakeApi({
      sharedListProjects: vi.fn(async () => ({
        projects: [{ id: 'p1', name: 'demo', publishedAt: '2026-07-10T00:00:00Z' }],
        lastSynced: '2026-07-17T00:00:00Z',
        stale: false,
      })),
    });
    const { result } = renderHook(() => usePublish({ enabled: true }), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });

    await waitFor(() => expect(result.current.configured).toBe(true));
    await waitFor(() => expect(fakeApi.sharedListProjects).toHaveBeenCalledWith({ refresh: false }));
    expect(fakeApi.getSharedStatus).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(result.current.publishedAtByProject.p1).toBe('2026-07-10T00:00:00Z'));
  });

  it('does not call sharedListProjects on mount when unconfigured', async () => {
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: false, url: null, publish: { state: 'idle' } })),
    });
    renderHook(() => usePublish({ enabled: true }), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });

    await act(async () => {});

    expect(fakeApi.sharedListProjects).not.toHaveBeenCalled();
  });


  it('reconciles publish state on re-enable after the job completed while disabled', async () => {
    // Server reports a running job at first...
    const getSharedStatus = vi.fn(async () => ({
      configured: true,
      publish: { state: 'running', project: 'p1' },
    }));
    const sharedListProjects = vi.fn(async () => ({
      projects: [{ id: 'p1', name: 'demo', publishedAt: '2026-07-17T00:00:00Z' }],
      lastSynced: '2026-07-17T00:00:00Z',
      stale: false,
    }));
    const fakeApi = makeFakeApi({ getSharedStatus, sharedListProjects });
    const { result, rerender } = renderHook(
      ({ enabled }) => usePublish({ enabled }),
      {
        wrapper: makeStableWrapper(fakeApi),
        initialProps: { enabled: true },
      }
    );

    // Mount enabled: the fresh status shows the running job; it's adopted.
    await waitFor(() => expect(result.current.publishState).toBe('running'));
    expect(result.current.publishingProject).toBe('p1');

    // User switches to the online tab: hook disabled, polling stops,
    // local state stays as-is (stale by design while away).
    await act(async () => {
      rerender({ enabled: false });
    });
    expect(result.current.publishState).toBe('running');
    expect(result.current.publishingProject).toBe('p1');

    // The job completes server-side while the hook is disabled.
    getSharedStatus.mockImplementation(async () => ({
      configured: true,
      publish: { state: 'done', project: 'p1' },
    }));
    await waitFor(() => expect(sharedListProjects.mock.calls.length).toBeGreaterThan(0));
    const listCallsBefore = sharedListProjects.mock.calls.length;

    // User returns to the local tab: hook re-enabled, status refetches.
    await act(async () => {
      rerender({ enabled: true });
    });

    // The wedge: without reconciliation, state stays 'running' forever.
    await waitFor(() => expect(result.current.publishState).toBe('done'));
    expect(result.current.publishingProject).toBeNull();
    // The done transition triggered the shared-list re-fetch (on top of the
    // configured-path fetch re-enabling the list query always does): exactly
    // 2 new calls.
    await waitFor(() => expect(sharedListProjects.mock.calls.length).toBe(listCallsBefore + 2));
    expect(sharedListProjects).toHaveBeenCalledWith({ refresh: false });
  });

  it('reconciles to error and surfaces it when the job failed while disabled', async () => {
    const getSharedStatus = vi.fn(async () => ({
      configured: true,
      publish: { state: 'running', project: 'p1' },
    }));
    const fakeApi = makeFakeApi({ getSharedStatus });
    const { result, rerender } = renderHook(
      ({ enabled }) => usePublish({ enabled }),
      {
        wrapper: makeStableWrapper(fakeApi),
        initialProps: { enabled: true },
      }
    );

    await waitFor(() => expect(result.current.publishState).toBe('running'));
    expect(result.current.publishingProject).toBe('p1');

    await act(async () => {
      rerender({ enabled: false });
    });

    // The job fails server-side while the hook is disabled.
    getSharedStatus.mockImplementation(async () => ({
      configured: true,
      publish: { state: 'error', project: 'p1', error: 'permission denied' },
    }));

    await act(async () => {
      rerender({ enabled: true });
    });

    await waitFor(() => expect(result.current.publishState).toBe('error'));
    expect(result.current.publishingProject).toBeNull();
    expect(result.current.publishError).toBe('permission denied');
    expect(result.current.publishErrorProject).toBe('p1');
  });

  // Minor 8 (final whole-branch review): CardFooter keys its inline error
  // banner on publishErrorProject alone (see ProjectsPage.jsx's CardFooter),
  // not on publishState. A rejected click on a DIFFERENT project (409, the
  // single-job guard -- see "does not clobber a genuinely running job" above)
  // leaves that project's card showing an error for as long as the tracked
  // job keeps running. Once that job's poll reports 'done', the lock is free
  // again and the stale error no longer describes reality -- it must clear.
  it('clears a stale error from a different (rejected) project once a poll reaches "done" for the tracked job', async () => {
    vi.useFakeTimers();
    try {
      const fakeApi = makeFakeApi();
      const { result } = renderHook(() => usePublish({ enabled: false }), {
        wrapper: ({ children }) => wrap(fakeApi, children),
      });

      // p1's publish genuinely starts and begins polling.
      await act(async () => {
        await result.current.publish('p1');
      });
      expect(result.current.publishState).toBe('running');

      // p2's click hits the backend's single-job guard and gets rejected.
      fakeApi.publishProject.mockRejectedValueOnce(new Error('a publish is already running'));
      await act(async () => {
        await result.current.publish('p2');
      });
      expect(result.current.publishError).toBe('a publish is already running');
      expect(result.current.publishErrorProject).toBe('p2');
      expect(result.current.publishState).toBe('running');

      // p1's job finishes -- the poll reports done.
      fakeApi.getSharedStatus.mockResolvedValue({ configured: true, publish: { state: 'done', project: 'p1', runs: 1 } });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });

      expect(result.current.publishState).toBe('done');
      expect(result.current.publishError).toBeNull();
      expect(result.current.publishErrorProject).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('does not leak an interval when unmounted while polling', async () => {
    vi.useFakeTimers();
    try {
      const getSharedStatus = vi.fn()
        .mockResolvedValueOnce({ configured: true, publish: { state: 'running', project: 'p1' } });
      const fakeApi = makeFakeApi({ getSharedStatus });
      const { unmount } = renderHook(() => usePublish({ enabled: true }), {
        wrapper: ({ children }) => wrap(fakeApi, children),
      });

      // Mount and start a publish (which starts polling).
      await act(async () => {
        // getSharedStatus was called once in loadStatus (sees running).
        expect(getSharedStatus).toHaveBeenCalledTimes(1);
      });

      // Unmount before any poll tick fires.
      unmount();

      // Advance timers past when a poll would have fired.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(4000);
      });

      // Must not have called getSharedStatus again after unmount.
      expect(getSharedStatus).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  // Audit C6: useSharedProjects and usePublish used to each fetch status
  // and list independently -- two of every request per Projects mount.
  // Both hooks now read `sharedKeys.status()`/`sharedKeys.list()`, so
  // react-query dedupes: mounting them together issues exactly one status
  // fetch and one list fetch, not one pair per hook.
  it('mounting alongside useSharedProjects issues exactly one status fetch and one list fetch (react-query dedup)', async () => {
    // Held open so the background revalidate useSharedProjects fires after
    // its own first successful list never completes during this test --
    // otherwise its own re-list would add a second, legitimate list fetch
    // and muddy the "exactly one" assertion this test is making.
    const refreshShared = vi.fn(() => new Promise(() => {}));
    const fakeApi = makeFakeApi({ refreshShared });

    function BothHooks() {
      useSharedProjects();
      return usePublish({ enabled: true });
    }

    renderHook(() => BothHooks(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });

    await waitFor(() => expect(fakeApi.getSharedStatus).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(fakeApi.sharedListProjects).toHaveBeenCalledTimes(1));
    // Give a would-be duplicate fetch (the bug this locks in against) a
    // chance to show up before asserting the counts hold steady.
    await act(async () => {});
    expect(fakeApi.getSharedStatus).toHaveBeenCalledTimes(1);
    expect(fakeApi.sharedListProjects).toHaveBeenCalledTimes(1);
  });
});
