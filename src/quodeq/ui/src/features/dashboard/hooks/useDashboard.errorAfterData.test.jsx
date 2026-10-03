import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useDashboard } from "./useDashboard";
import { withStableQueryApi } from "../../../test-utils/withQueryClient.jsx";
import { ERROR_RETRY_MS } from "../../../hooks/queryDefaults.js";

// The sibling errorRecovery test covers a query that never loaded. This one
// covers the state the user actually sees: the Overview already holds a
// payload, a BACKGROUND refetch fails (server restart, slow score cache),
// and the inline "Failed to load dashboard data" line appears above live
// content. It must clear on its own once the server answers again.

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
    return { accumulated: { score: 90 }, trend: [], availableRuns: [{ runId: "r1", status: "done" }] };
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

async function loadHealthy(selectedRun) {
  const state = { fail: false };
  const api = makeFlakyApi(state);
  const rendered = renderHook(
    () => useDashboard({ selectedProject: "p1", selectedRun }),
    { wrapper: withStableQueryApi(api) },
  );
  await act(async () => { await vi.advanceTimersByTimeAsync(50); });
  expect(rendered.result.current.error).toBeNull();
  expect(rendered.result.current.dashboard).not.toBeNull();
  return { state, api, ...rendered };
}

describe("useDashboard error after data", () => {
  it("clears the inline error once a failed background refetch succeeds again (latest)", async () => {
    vi.useFakeTimers();
    const { state, result } = await loadHealthy(null);

    // Server goes away; an active invalidation refetches and fails.
    state.fail = true;
    await act(async () => { result.current.refreshDashboardActive(); });
    await act(async () => { await vi.advanceTimersByTimeAsync(50); });
    expect(result.current.error).toBeTruthy();
    expect(result.current.dashboard).not.toBeNull();

    // Server recovers. Only the error-retry interval can clear the line.
    state.fail = false;
    await act(async () => { await vi.advanceTimersByTimeAsync(ERROR_RETRY_MS + 100); });
    expect(result.current.error).toBeNull();
  });

  it("clears the inline error once a failed background refetch succeeds again (frozen run)", async () => {
    vi.useFakeTimers();
    const { state, result } = await loadHealthy("r1");

    state.fail = true;
    await act(async () => { result.current.refreshDashboardActive(); });
    await act(async () => { await vi.advanceTimersByTimeAsync(50); });
    expect(result.current.error).toBeTruthy();
    expect(result.current.dashboard).not.toBeNull();

    state.fail = false;
    await act(async () => { await vi.advanceTimersByTimeAsync(ERROR_RETRY_MS + 100); });
    expect(result.current.error).toBeNull();
  });
});
