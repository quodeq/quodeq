import React from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { ApiProvider } from '../../../api/ApiContext.jsx';
import { withStableQueryApi } from '../../../test-utils/withQueryClient.jsx';
import { usePrincipleData, useExplorerData } from './explorerDataHooks.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';

// ---------------------------------------------------------------------------
// Shared test fixtures
// ---------------------------------------------------------------------------

const EVAL_PRINCIPAL = {
  principle: 'Input Validation',
  dimension: 'Security',
  project: 'proj',
  runId: 'r1',
  principleData: { violations: [], compliance: [] },
  dimViolations: [],
  dimCompliance: [],
  score: '7.0/10',
  grade: 'B',
  dateLabel: '',
};

// Shape returned by POST /api/findings/dismiss with run_id supplied.
const DISMISS_RESPONSE = {
  scores: {
    dimensions: [{
      dimension: 'Security',
      overallScore: '6.0/10',
      overallGrade: 'C',
      principles: [{ principle: 'Input Validation', score: '6.5/10', grade: 'C+' }],
    }],
    summary: { overallGrade: 'C', numericAverage: 6.0 },
  },
};

// ---------------------------------------------------------------------------
// API mock — usePrincipleData no longer touches the API directly. It receives
// the dismiss handler from the caller (App.jsx) and treats its resolved value
// as the source of truth for the new score.
// ---------------------------------------------------------------------------

function wrapper({ children }) {
  return <ApiProvider value={{}}>{children}</ApiProvider>;
}

describe('usePrincipleData', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('updates liveScore/liveGrade from the dismiss response payload', async () => {
    const onDismiss = vi.fn(async () => DISMISS_RESPONSE);
    const { result } = renderHook(
      () => usePrincipleData(EVAL_PRINCIPAL, null, onDismiss),
      { wrapper },
    );

    await act(async () => {
      await result.current.handleDismiss({ file: 'a.py', line: 10, principle: 'Input Validation' });
    });

    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(result.current.liveScore).toBe('6.5/10');
    expect(result.current.liveGrade).toBe('C+');
  });

  it('keeps the violation in the dismissed set so it disappears from the list', async () => {
    const onDismiss = vi.fn(async () => DISMISS_RESPONSE);
    const { result } = renderHook(
      () => usePrincipleData(EVAL_PRINCIPAL, null, onDismiss),
      { wrapper },
    );

    await act(async () => {
      await result.current.handleDismiss({ file: 'a.py', line: 10, principle: 'Input Validation' });
    });

    expect(result.current.dismissedSet.has('a.py:10')).toBe(true);
  });

  it('rolls back the optimistic dismiss when the POST fails', async () => {
    const onDismiss = vi.fn(async () => { throw new Error('network down'); });
    const { result } = renderHook(
      () => usePrincipleData(EVAL_PRINCIPAL, null, onDismiss),
      { wrapper },
    );

    await act(async () => {
      await result.current.handleDismiss({ file: 'a.py', line: 10, principle: 'Input Validation' });
    });

    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(result.current.dismissedSet.has('a.py:10')).toBe(false);
    expect(result.current.liveScore).toBeNull();
    expect(result.current.liveGrade).toBeNull();
  });

  it('does nothing when no onDismiss prop is provided', async () => {
    const { result } = renderHook(
      () => usePrincipleData(EVAL_PRINCIPAL, null, null),
      { wrapper },
    );

    await act(async () => {
      await result.current.handleDismiss({ file: 'a.py', line: 10, principle: 'Input Validation' });
    });

    // No throw, no state change — the dismissed-set stays empty.
    expect(result.current.dismissedSet.size).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Task 17: useExplorerData source-aware fetch selection. A shared-source
// selection must read dimension eval + run scores from the shared-repo
// mirror endpoints, never the local ones.
// ---------------------------------------------------------------------------

function makeFakeExplorerApi() {
  return {
    getDimensionEval: vi.fn(async () => ({ dimension: 'security', principles: [], principleGrades: [] })),
    getRunScores: vi.fn(async () => ({ dimensions: [] })),
    sharedGetDimensionEval: vi.fn(async () => ({ dimension: 'security', principles: [], principleGrades: [], marker: 'shared' })),
    sharedGetRunScores: vi.fn(async () => ({ dimensions: [], marker: 'shared' })),
  };
}

describe('useExplorerData source-aware fetch selection', () => {
  it("calls getDimensionEval/getRunScores (not the shared variants) when selectedSource is 'local' (default)", async () => {
    const fakeApi = makeFakeExplorerApi();
    const { result } = renderHook(
      () => useExplorerData('proj', 'security', 'r1', null),
      { wrapper: withStableQueryApi(fakeApi) },
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(fakeApi.getDimensionEval).toHaveBeenCalledWith('proj', 'r1', 'security');
    expect(fakeApi.getRunScores).toHaveBeenCalledWith('proj', 'r1');
    expect(fakeApi.sharedGetDimensionEval).not.toHaveBeenCalled();
    expect(fakeApi.sharedGetRunScores).not.toHaveBeenCalled();
  });

  it("calls sharedGetDimensionEval/sharedGetRunScores (not the local variants) when selectedSource is 'shared'", async () => {
    const fakeApi = makeFakeExplorerApi();
    const { result } = renderHook(
      () => useExplorerData('proj', 'security', 'r1', null, 'shared'),
      { wrapper: withStableQueryApi(fakeApi) },
    );
    await waitFor(() => expect(result.current.evalData?.marker).toBe('shared'));
    expect(fakeApi.sharedGetDimensionEval).toHaveBeenCalledWith('proj', 'r1', 'security');
    expect(fakeApi.sharedGetRunScores).toHaveBeenCalledWith('proj', 'r1');
    expect(fakeApi.getDimensionEval).not.toHaveBeenCalled();
    expect(fakeApi.getRunScores).not.toHaveBeenCalled();
  });
});

describe('useExplorerData response handling', () => {
  it('ignores a stale response that resolves after a newer request', async () => {
    // Run-navigator clicks re-key the query; a slow earlier response
    // resolving last must land in ITS OWN cache entry, never under the
    // current run's header.
    const resolvers = {};
    const fakeApi = {
      getDimensionEval: vi.fn((p, r) => new Promise((res) => { resolvers[r] = res; })),
      getRunScores: vi.fn(async () => null),
      sharedGetDimensionEval: vi.fn(),
      sharedGetRunScores: vi.fn(),
    };
    const { result, rerender } = renderHook(
      ({ runId }) => useExplorerData('proj', 'security', runId, null),
      { initialProps: { runId: 'r1' }, wrapper: withStableQueryApi(fakeApi) },
    );
    rerender({ runId: 'r2' });
    await act(async () => { resolvers.r2({ dimension: 'security', marker: 'r2' }); });
    await waitFor(() => expect(result.current.evalData?.marker).toBe('r2'));
    // The stale r1 response must land in its own cache entry, not on screen.
    await act(async () => { resolvers.r1({ dimension: 'security', marker: 'r1' }); });
    expect(result.current.evalData?.marker).toBe('r2');
  });

  it('flags a waiting (202) payload instead of presenting it as a report', async () => {
    // The backend returns {waiting: true} while evaluation/<dim>.json is not
    // written yet; rendering it as data showed SCORE — / 0 violations,
    // indistinguishable from a genuinely clean dimension.
    const fakeApi = {
      getDimensionEval: vi.fn(async () => ({ waiting: true, project: 'proj', run: 'r1', dimension: 'security' })),
      getRunScores: vi.fn(async () => null),
      sharedGetDimensionEval: vi.fn(),
      sharedGetRunScores: vi.fn(),
    };
    const { result } = renderHook(
      () => useExplorerData('proj', 'security', 'r1', null),
      { wrapper: withStableQueryApi(fakeApi) },
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.waiting).toBe(true);
  });

  it('re-enters from cache without a loading pass (the Back-nav path)', async () => {
    // Back from a principle detail remounts ExplorerPage. With the queries
    // in the shared cache the remount renders data immediately — loading
    // must stay false from the first render or the page flashes the
    // full-screen LoadingScreen it used to show on every Back.
    // withStableQueryApi's client uses gcTime: 0, which drops the cache the
    // moment the first mount unmounts — exactly the continuity this test is
    // about — so it needs a client with a real gcTime.
    const fakeApi = makeFakeExplorerApi();
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 300_000, staleTime: 60_000 } },
    });
    const wrapper = ({ children }) => (
      <QueryClientProvider client={client}>
        <ApiProvider value={fakeApi}>{children}</ApiProvider>
      </QueryClientProvider>
    );
    const first = renderHook(() => useExplorerData('proj', 'security', 'r1', null), { wrapper });
    await waitFor(() => expect(first.result.current.loading).toBe(false));
    first.unmount();

    const second = renderHook(() => useExplorerData('proj', 'security', 'r1', null), { wrapper });
    expect(second.result.current.loading).toBe(false);
    expect(second.result.current.evalData).toBeTruthy();
  });

  it('eval query error is mapped through apiErrorMessage', async () => {
    // AUTH_REQUIRED is a mapped code, so its friendly text diverges from the
    // raw backend message -- that divergence is what makes this test fail
    // against the old `evalQuery.error?.message` code.
    const err = Object.assign(new Error('raw fetch failure'), { code: 'AUTH_REQUIRED' });
    const fakeApi = {
      getDimensionEval: vi.fn().mockRejectedValue(err),
      getRunScores: vi.fn(async () => null),
      sharedGetDimensionEval: vi.fn(),
      sharedGetRunScores: vi.fn(),
    };
    const { result } = renderHook(
      () => useExplorerData('proj', 'security', 'r1', null),
      { wrapper: withStableQueryApi(fakeApi) },
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe(apiErrorMessage(err, 'explorer.loadFailed'));
    expect(result.current.error).not.toBe(err.message);
  });

  it('merges the rescored per-dimension grades over the raw eval payload', async () => {
    const fakeApi = {
      getDimensionEval: vi.fn(async () => ({
        dimension: 'security',
        principleGrades: [
          { principle: 'Input Validation', score: '8.0/10', grade: 'B' },
          { principle: 'Overall', score: '8.0/10', grade: 'B', isOverall: true },
        ],
        violations: [],
      })),
      getRunScores: vi.fn(async () => ({
        dimensions: [{
          dimension: 'security',
          overallScore: '6.0/10',
          overallGrade: 'C',
          principles: [{ principle: 'Input Validation', score: '6.5/10', grade: 'C+' }],
        }],
      })),
      sharedGetDimensionEval: vi.fn(),
      sharedGetRunScores: vi.fn(),
    };
    const { result } = renderHook(
      () => useExplorerData('proj', 'security', 'r1', null),
      { wrapper: withStableQueryApi(fakeApi) },
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    const pg = result.current.principleGrades.find((p) => p.principle === 'Input Validation');
    expect(pg.score).toBe('6.5/10');
    expect(result.current.overallGrade.score).toBe('6.0/10');
  });
});
