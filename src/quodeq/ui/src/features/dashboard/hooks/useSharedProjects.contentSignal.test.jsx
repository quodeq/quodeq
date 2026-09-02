import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useSharedProjects, useSharedContentSignal } from './useSharedProjects.js';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { sharedKeys } from '../../../api/queryKeys.js';

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


// Split from useSharedProjects.test.jsx: useSharedContentSignal, the
// passive local-projects-empty signal (no background refresh).

// The passive signal App.jsx uses to decide the zero-local-projects flow
// (wizard auto-open, landing redirect, empty-state copy). Same cache keys as
// useSharedProjects, but no background refresh — mounting it must never
// trigger a POST /api/shared/refresh.
describe('useSharedContentSignal', () => {
  it('settles with hasContent=false when no shared repo is configured, without listing', async () => {
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: false })),
    });
    const { result } = renderHook(() => useSharedContentSignal(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });
    await waitFor(() => expect(result.current.settled).toBe(true));
    expect(result.current.hasContent).toBe(false);
    expect(fakeApi.sharedListProjects).not.toHaveBeenCalled();
  });

  it('reports hasContent=true when configured and the list has projects', async () => {
    const fakeApi = makeFakeApi();
    const { result } = renderHook(() => useSharedContentSignal(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });
    await waitFor(() => expect(result.current.settled).toBe(true));
    expect(result.current.hasContent).toBe(true);
  });

  it('reports hasContent=false when configured but the list is empty', async () => {
    const fakeApi = makeFakeApi({
      sharedListProjects: vi.fn(async () => ({ projects: [], lastSynced: null, stale: false })),
    });
    const { result } = renderHook(() => useSharedContentSignal(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });
    await waitFor(() => expect(result.current.settled).toBe(true));
    expect(result.current.hasContent).toBe(false);
  });

  it('settles with hasContent=false when the status fetch fails (fallback to local-only flow)', async () => {
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => { throw new Error('boom'); }),
    });
    const { result } = renderHook(() => useSharedContentSignal(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });
    await waitFor(() => expect(result.current.settled).toBe(true));
    expect(result.current.hasContent).toBe(false);
  });

  it('is not settled while the status fetch is in flight', async () => {
    const d = deferred();
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(() => d.promise),
    });
    const { result } = renderHook(() => useSharedContentSignal(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });
    expect(result.current.settled).toBe(false);
    d.resolve({ configured: false });
    await waitFor(() => expect(result.current.settled).toBe(true));
  });

  it('never triggers a background refresh on its own', async () => {
    const fakeApi = makeFakeApi();
    const { result } = renderHook(() => useSharedContentSignal(), {
      wrapper: ({ children }) => wrap(fakeApi, children),
    });
    await waitFor(() => expect(result.current.settled).toBe(true));
    expect(fakeApi.refreshShared).not.toHaveBeenCalled();
  });
});
