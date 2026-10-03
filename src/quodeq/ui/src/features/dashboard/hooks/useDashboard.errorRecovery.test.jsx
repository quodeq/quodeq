import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useDashboard } from "./useDashboard";
import { withStableQueryApi } from "../../../test-utils/withQueryClient.jsx";
import { ERROR_RETRY_MS } from "../../../hooks/queryDefaults.js";

// The desktop webview never blurs, so refetchOnWindowFocus (the browser's
// natural recovery path after a failed fetch) never fires there. A dashboard
// or scores query that exhausted its retries used to park on "Couldn't load
// this project" forever, even after the server recovered — the only way out
// was navigating away and back. These tests pin the error-retry interval:
// a query sitting in error state must refetch on its own and clear the
// error once the backend answers again, with no remount and no focus event.

function makeDashboardPayload() {
  return {
    project: "p1",
    run: "latest",
    trend: [],
    summary: { score: 75 },
    dimensions: [],
    selectedRun: { runId: "r1", dateLabel: "2026-05-01" },
  };
}

function makeFlakyApi(state) {
  const failing = async () => {
    if (state.fail) throw new Error("HTTP 500");
    return makeDashboardPayload();
  };
  const failingScores = async () => {
    if (state.fail) throw new Error("HTTP 500");
    return { accumulated: { score: 90 }, trend: [], availableRuns: [] };
  };
  return {
    getDashboard: vi.fn(failing),
    sharedGetDashboard: vi.fn(failing),
    getProjectScores: vi.fn(failingScores),
    sharedGetProjectScores: vi.fn(failingScores),
    sharedGetProjectInfo: vi.fn(async () => ({})),
  };
}

afterEach(() => {
  vi.useRealTimers();
});

describe("useDashboard error recovery", () => {
  it("self-heals after the backend recovers, without remount or focus", async () => {
    vi.useFakeTimers();
    const state = { fail: true };
    const api = makeFlakyApi(state);

    const { result } = renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: null }),
      { wrapper: withStableQueryApi(api) },
    );

    // Initial fetches reject (retry is off in the test client).
    await act(async () => { await vi.advanceTimersByTimeAsync(50); });
    expect(result.current.error).toBeTruthy();
    expect(result.current.dashboard).toBeNull();

    // Backend recovers. Nothing else happens: no remount, no focus event,
    // no invalidation. Only the error-retry interval can save us.
    state.fail = false;
    await act(async () => { await vi.advanceTimersByTimeAsync(ERROR_RETRY_MS + 100); });

    expect(result.current.error).toBeNull();
    expect(result.current.dashboard).not.toBeNull();
    expect(result.current.dashboard.summary).toEqual({ score: 75 });
  });

  it("does not keep polling once the query is healthy again", async () => {
    vi.useFakeTimers();
    const state = { fail: true };
    const api = makeFlakyApi(state);

    renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: null }),
      { wrapper: withStableQueryApi(api) },
    );

    await act(async () => { await vi.advanceTimersByTimeAsync(50); });
    state.fail = false;
    await act(async () => { await vi.advanceTimersByTimeAsync(ERROR_RETRY_MS + 100); });
    const callsAfterRecovery = api.getDashboard.mock.calls.length;

    // Two more interval windows: a recovered query must not refetch again
    // (staleTime still governs routine freshness, not the error interval).
    await act(async () => { await vi.advanceTimersByTimeAsync(2 * ERROR_RETRY_MS); });
    expect(api.getDashboard.mock.calls.length).toBe(callsAfterRecovery);
  });
});
