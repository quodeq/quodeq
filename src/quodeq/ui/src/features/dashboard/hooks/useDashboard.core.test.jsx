import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useDashboard } from "./useDashboard";
import { withQueryClient, withStableQueryApi } from "../../../test-utils/withQueryClient.jsx";
import { ApiProvider } from "../../../api/ApiContext.jsx";
import { projectKeys } from "../../../api/queryKeys.js";

function makeDashboardPayload(overrides = {}) {
  return {
    project: "p1",
    run: "latest",
    trend: [],
    summary: { score: 75 },
    dimensions: [
      { dimension: "Security", overallScore: "7.0/10", overallGrade: "B", violations: [], compliance: [], principles: [] },
    ],
    selectedRun: { runId: "r1", dateLabel: "2026-05-01" },
    ...overrides,
  };
}

function makeFakeApi() {
  return {
    getDashboard: vi.fn(async (project, run) => makeDashboardPayload({ project, run: run || "latest" })),
    sharedGetDashboard: vi.fn(async (project, run) => makeDashboardPayload({ project, run: run || "latest", marker: "shared" })),
    getProjectScores: vi.fn(async () => ({
      accumulated: { score: 90 },
      trend: [],
      availableRuns: [],
    })),
    sharedGetProjectScores: vi.fn(async () => ({
      accumulated: { score: 55 },
      trend: [],
      availableRuns: [],
    })),
    sharedGetProjectInfo: vi.fn(async (project) => ({ id: project, name: project, publishedBy: 'ana', publishedAt: 1752710400000 })),
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

// Split from useDashboard.test.jsx: the base useDashboard behavior,
// scheduleDashboardReconcile debouncing, and source-aware fetch selection.

describe("useDashboard", () => {
  it("returns nulls when project is empty", () => {
    const fakeApi = makeFakeApi();
    const { result } = renderHook(
      () => useDashboard({ selectedProject: "", selectedRun: null }),
      { wrapper: ({ children }) => wrap(fakeApi, children) },
    );
    expect(result.current.dashboard).toBeNull();
    expect(result.current.accumulated).toBeNull();
  });

  it("fetches dashboard data for the selected project", async () => {
    const fakeApi = makeFakeApi();
    const { result } = renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: null }),
      { wrapper: ({ children }) => wrap(fakeApi, children) },
    );
    await waitFor(() => {
      expect(result.current.dashboard?.summary?.score).toBe(75);
    });
  });

  it("merges trend from scores into the dashboard payload", async () => {
    const fakeApi = makeFakeApi();
    const { result } = renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: null }),
      { wrapper: ({ children }) => wrap(fakeApi, children) },
    );
    await waitFor(() => {
      expect(Array.isArray(result.current.dashboard?.trend)).toBe(true);
    });
  });

  it("exposes refreshDashboard for invalidating the cache after a dismiss", async () => {
    const fakeApi = makeFakeApi();
    const { result } = renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: null }),
      { wrapper: ({ children }) => wrap(fakeApi, children) },
    );
    await waitFor(() => expect(result.current.dashboard).not.toBeNull());
    expect(typeof result.current.refreshDashboard).toBe("function");
  });

  // The dismiss path must stay lazy: invalidating with refetchType:'none'
  // marks the cache stale but must NOT refetch the mounted observer (the
  // dashboard payload is 10-20 MB; refetching on every dismiss froze the UI).
  it("refreshDashboard does NOT refetch the mounted observer (lazy dismiss path)", async () => {
    const fakeApi = makeFakeApi();
    const { result } = renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: null }),
      { wrapper: ({ children }) => wrap(fakeApi, children) },
    );
    await waitFor(() => expect(result.current.dashboard).not.toBeNull());
    expect(fakeApi.getDashboard).toHaveBeenCalledTimes(1);

    await act(async () => {
      await result.current.refreshDashboard();
    });
    // Give any errant refetch a chance to fire, then assert it didn't.
    await new Promise((r) => setTimeout(r, 50));
    expect(fakeApi.getDashboard).toHaveBeenCalledTimes(1);
  });

  // refreshDashboardActive must actively refetch the always-mounted Overview
  // observer — e.g. the manual retry path (App.jsx's onRetry) — otherwise a
  // stale (often null) payload lingers until the user switches projects.
  it("refreshDashboardActive refetches the mounted observer (manual retry path)", async () => {
    const fakeApi = makeFakeApi();
    const { result } = renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: null }),
      { wrapper: ({ children }) => wrap(fakeApi, children) },
    );
    await waitFor(() => expect(result.current.dashboard).not.toBeNull());
    expect(fakeApi.getDashboard).toHaveBeenCalledTimes(1);
    expect(typeof result.current.refreshDashboardActive).toBe("function");

    await act(async () => {
      await result.current.refreshDashboardActive();
    });
    await waitFor(() => expect(fakeApi.getDashboard).toHaveBeenCalledTimes(2));
  });
});

// After restore-all/delete-all, the mutation response carries scores:null /
// delta.isLatest:false — applyMutationDelta's gates are a no-op — so
// refreshDashboard's lazy (refetchType:'none') invalidation is the ONLY
// signal the Overview ever gets, and its always-mounted observer never
// refetches on its own (no remount, and the desktop pywebview window never
// fires a focus refetch). scheduleDashboardReconcile is the debounced ACTIVE
// counterpart the suppression-mutation handlers call alongside
// refreshDashboard so restored/deleted findings actually reappear.
describe("useDashboard scheduleDashboardReconcile (debounced active reconcile)", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  function renderWithSpy() {
    const fakeApi = makeFakeApi();
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
    });
    const spy = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: null }),
      {
        wrapper: ({ children }) => (
          <QueryClientProvider client={client}>
            <ApiProvider value={fakeApi}>{children}</ApiProvider>
          </QueryClientProvider>
        ),
      },
    );
    return { result, spy };
  }

  // Schedule-time mark-stale (hardening): if the debounce timer never fires
  // (e.g. a rapid project switch clears the single shared timer ref before
  // 1200ms elapses), the mutation must still have left the cache stale --
  // otherwise a dropped reconcile silently leaves fresh-looking-but-wrong
  // data cached instead of degrading to refreshDashboard's mark-stale-only
  // contract. Scheduling call synchronously invalidates with
  // refetchType:'none' BEFORE the timer is armed, then the timer still does
  // the ACTIVE invalidation after the debounce window.
  it("marks the subtree stale (refetchType:'none') synchronously at schedule time, before the timer fires", () => {
    const { result, spy } = renderWithSpy();
    act(() => result.current.scheduleDashboardReconcile());
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy.mock.calls[0][0].refetchType).toBe("none");
    expect(spy.mock.calls[0][0].queryKey).toEqual(projectKeys.project("p1", "local"));
  });

  it("invalidates the project subtree with an ACTIVE refetch after the debounce window", () => {
    const { result, spy } = renderWithSpy();
    act(() => result.current.scheduleDashboardReconcile());
    act(() => { vi.advanceTimersByTime(1200); });
    // The ACTIVE (no refetchType) call is the one without refetchType:'none'.
    const activeCalls = spy.mock.calls.filter(([arg]) => arg.refetchType === undefined);
    expect(activeCalls).toHaveLength(1);
    expect(activeCalls[0][0].queryKey).toEqual(projectKeys.project("p1", "local"));
  });

  it("coalesces rapid calls into exactly one ACTIVE invalidation (multiple 'none' pre-marks are fine)", () => {
    const { result, spy } = renderWithSpy();
    act(() => {
      result.current.scheduleDashboardReconcile();
      vi.advanceTimersByTime(600);
      result.current.scheduleDashboardReconcile(); // resets the timer
      vi.advanceTimersByTime(600);
      result.current.scheduleDashboardReconcile();
    });
    act(() => { vi.advanceTimersByTime(1200); });
    const activeCalls = spy.mock.calls.filter(([arg]) => arg.refetchType === undefined);
    expect(activeCalls).toHaveLength(1);
  });

  // Regression pin: the debounced reconcile is additive, not a replacement.
  // refreshDashboard must keep its lazy refetchType:'none' contract for its
  // other callers (wizard project registration, dismiss/restore, etc.).
  it("refreshDashboard keeps mark-stale-only behavior (regression pin)", () => {
    const { result, spy } = renderWithSpy();
    act(() => result.current.refreshDashboard());
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy.mock.calls[0][0].refetchType).toBe("none");
  });
});

// Task 17: source-aware fetch selection. selectedSource picks which
// endpoint family (local vs shared-repo mirror) backs every query this hook
// issues, and it must never leak into the wrong fetcher.
describe("useDashboard source-aware fetch selection", () => {
  it("calls getDashboard/getProjectScores (not the shared variants) when selectedSource is 'local' (default)", async () => {
    const fakeApi = makeFakeApi();
    const { result } = renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: null }),
      { wrapper: ({ children }) => wrap(fakeApi, children) },
    );
    await waitFor(() => expect(result.current.dashboard).not.toBeNull());
    expect(fakeApi.getDashboard).toHaveBeenCalledWith("p1", null);
    expect(fakeApi.sharedGetDashboard).not.toHaveBeenCalled();
    expect(fakeApi.getProjectScores).toHaveBeenCalled();
    expect(fakeApi.sharedGetProjectScores).not.toHaveBeenCalled();
  });

  it("calls sharedGetDashboard/sharedGetProjectScores (not the local variants) when selectedSource is 'shared'", async () => {
    const fakeApi = makeFakeApi();
    const { result } = renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: null, selectedSource: "shared" }),
      { wrapper: ({ children }) => wrap(fakeApi, children) },
    );
    await waitFor(() => expect(result.current.dashboard?.marker).toBe("shared"));
    expect(fakeApi.sharedGetDashboard).toHaveBeenCalledWith("p1", null);
    expect(fakeApi.getDashboard).not.toHaveBeenCalled();
    expect(fakeApi.sharedGetProjectScores).toHaveBeenCalled();
    expect(fakeApi.getProjectScores).not.toHaveBeenCalled();
  });

  // Cache-isolation: switching source for the SAME projectId must never serve
  // the other source's cached payload -- each source issues its own fetch.
  it("never serves a cross-source cache hit when the source flips for the same project", async () => {
    const fakeApi = makeFakeApi();
    const QC = withQueryClient();
    const { result, rerender } = renderHook(
      ({ selectedSource }) => useDashboard({ selectedProject: "p1", selectedRun: null, selectedSource }),
      {
        wrapper: ({ children }) => (
          <QC>
            <ApiProvider value={fakeApi}>{children}</ApiProvider>
          </QC>
        ),
        initialProps: { selectedSource: "local" },
      },
    );
    await waitFor(() => expect(result.current.dashboard).not.toBeNull());
    expect(fakeApi.getDashboard).toHaveBeenCalledTimes(1);
    expect(fakeApi.sharedGetDashboard).not.toHaveBeenCalled();

    rerender({ selectedSource: "shared" });
    await waitFor(() => expect(result.current.dashboard?.marker).toBe("shared"));
    // The shared fetch actually fired -- it did NOT reuse the local entry.
    expect(fakeApi.sharedGetDashboard).toHaveBeenCalledTimes(1);
    // And flipping didn't re-trigger the local fetch either.
    expect(fakeApi.getDashboard).toHaveBeenCalledTimes(1);
  });
});
