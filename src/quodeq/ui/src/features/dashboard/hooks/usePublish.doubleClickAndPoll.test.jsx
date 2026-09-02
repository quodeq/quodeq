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

// Split from usePublish.test.jsx: publish() double-submit guard,
// running-state transition, and the 2s status-poll to completion.

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
});
