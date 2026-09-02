import { describe, it, expect, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { usePublish } from './usePublish.js';
import { useSharedProjects } from './useSharedProjects.js';
import { withQueryClient, withStableQueryApi } from '../../../test-utils/withQueryClient.jsx';
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

// Rerender-safe wrapper. See withStableQueryApi's doc comment for why the
// inline `({ children }) => wrap(fakeApi, children)` idiom above must not be
// used by any test that rerenders.
const makeStableWrapper = withStableQueryApi;

// Split from usePublish.test.jsx: the optimistic list-cache patch on
// completion, POST-error surfacing, and mount-fetch gating.

describe('usePublish', () => {
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
});
