import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useDashboard } from "./useDashboard";
import { withQueryClient } from "../../../test-utils/withQueryClient.jsx";
import { ApiProvider } from "../../../api/ApiContext.jsx";
import { projectKeys } from "../../../api/queryKeys.js";
import { getProjectScores } from "../../../api/index.js";

const fakeApi = {
  getDashboard: vi.fn(async (project, run) => ({
    project,
    run: run || "latest",
    trend: [],
    summary: { score: 75 },
    dimensions: [
      { dimension: "Security", overallScore: "7.0/10", overallGrade: "B", violations: [], compliance: [], principles: [] },
    ],
    selectedRun: { runId: "r1", dateLabel: "2026-05-01" },
  })),
};

vi.mock("../../../api/index.js", () => ({
  getProjectScores: vi.fn(async () => ({
    accumulated: { score: 90 },
    trend: [],
    availableRuns: [],
  })),
}));

function wrap(children) {
  const QC = withQueryClient();
  return (
    <QC>
      <ApiProvider value={fakeApi}>{children}</ApiProvider>
    </QC>
  );
}

describe("useDashboard", () => {
  it("returns nulls when project is empty", () => {
    const { result } = renderHook(
      () => useDashboard({ selectedProject: "", selectedRun: null }),
      { wrapper: ({ children }) => wrap(children) },
    );
    expect(result.current.dashboard).toBeNull();
    expect(result.current.accumulated).toBeNull();
  });

  it("fetches dashboard data for the selected project", async () => {
    const { result } = renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: null }),
      { wrapper: ({ children }) => wrap(children) },
    );
    await waitFor(() => {
      expect(result.current.dashboard?.summary?.score).toBe(75);
    });
  });

  it("merges trend from scores into the dashboard payload", async () => {
    const { result } = renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: null }),
      { wrapper: ({ children }) => wrap(children) },
    );
    await waitFor(() => {
      expect(Array.isArray(result.current.dashboard?.trend)).toBe(true);
    });
  });

  it("exposes refreshDashboard for invalidating the cache after a dismiss", async () => {
    const { result } = renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: null }),
      { wrapper: ({ children }) => wrap(children) },
    );
    await waitFor(() => expect(result.current.dashboard).not.toBeNull());
    expect(typeof result.current.refreshDashboard).toBe("function");
  });

  // The dismiss path must stay lazy: invalidating with refetchType:'none'
  // marks the cache stale but must NOT refetch the mounted observer (the
  // dashboard payload is 10-20 MB; refetching on every dismiss froze the UI).
  it("refreshDashboard does NOT refetch the mounted observer (lazy dismiss path)", async () => {
    fakeApi.getDashboard.mockClear();
    const { result } = renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: null }),
      { wrapper: ({ children }) => wrap(children) },
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

  // The eval-completion path must actively refetch the always-mounted Overview
  // observer — otherwise a freshly-finished run leaves the Overview showing the
  // stale (often null) pre-run payload until the user switches projects.
  it("refreshDashboardActive refetches the mounted observer (eval-completion path)", async () => {
    fakeApi.getDashboard.mockClear();
    const { result } = renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: null }),
      { wrapper: ({ children }) => wrap(children) },
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

// A completed historical run's payload is immutable apart from explicit
// mutations (dismiss/delete/formula), which invalidate the project subtree.
// These tests pin the freeze contract: cached completed runs never refetch
// on remount (no dashboard-refreshing dim flash), while 'latest',
// in-progress runs, and invalidated entries still do.
describe("useDashboard frozen historical runs", () => {
  const OLD = () => Date.now() - 120_000; // well past the 60s staleTime

  function seededClient({ runStatus = "complete" } = {}) {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 60_000 }, mutations: { retry: false } },
    });
    // Fresh latest-scores entry: run statuses resolve synchronously, no fetch.
    client.setQueryData(
      projectKeys.scores("p1", null),
      { accumulated: { score: 90 }, trend: [], availableRuns: [{ runId: "r1", status: runStatus }] },
      { updatedAt: Date.now() },
    );
    // Stale entries for the run itself.
    client.setQueryData(
      projectKeys.dashboard("p1", "r1"),
      { marker: "cached", trend: [], dimensions: [], selectedRun: { runId: "r1" } },
      { updatedAt: OLD() },
    );
    client.setQueryData(
      projectKeys.scores("p1", "r1"),
      { accumulated: { score: 80 }, trend: [] },
      { updatedAt: OLD() },
    );
    return client;
  }

  function wrapWith(client) {
    return ({ children }) => (
      <QueryClientProvider client={client}>
        <ApiProvider value={fakeApi}>{children}</ApiProvider>
      </QueryClientProvider>
    );
  }

  it("serves a cached completed run without any refetch", async () => {
    fakeApi.getDashboard.mockClear();
    getProjectScores.mockClear();
    const client = seededClient();
    const { result } = renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: "r1", keepPlaceholder: false }),
      { wrapper: wrapWith(client) },
    );
    await waitFor(() => expect(result.current.dashboard).not.toBeNull());
    expect(result.current.dashboard.marker).toBe("cached");
    // Give any errant background refetch a chance to fire, then assert quiet.
    await new Promise((r) => setTimeout(r, 50));
    expect(fakeApi.getDashboard).not.toHaveBeenCalled();
    expect(getProjectScores).not.toHaveBeenCalled();
  });

  it("still refetches a stale in-progress run", async () => {
    fakeApi.getDashboard.mockClear();
    const client = seededClient({ runStatus: "in_progress" });
    renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: "r1", keepPlaceholder: false }),
      { wrapper: wrapWith(client) },
    );
    await waitFor(() => expect(fakeApi.getDashboard).toHaveBeenCalledWith("p1", "r1"));
  });

  it("still refetches a stale latest selection", async () => {
    fakeApi.getDashboard.mockClear();
    const client = seededClient();
    client.setQueryData(
      projectKeys.dashboard("p1", null),
      { marker: "cached-latest", trend: [], dimensions: [] },
      { updatedAt: OLD() },
    );
    renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: null, keepPlaceholder: false }),
      { wrapper: wrapWith(client) },
    );
    await waitFor(() => expect(fakeApi.getDashboard).toHaveBeenCalledWith("p1", null));
  });

  it("refetches a frozen run after invalidation (dismiss/delete contract)", async () => {
    fakeApi.getDashboard.mockClear();
    const client = seededClient();
    await client.invalidateQueries({ queryKey: projectKeys.project("p1"), refetchType: "none" });
    renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: "r1", keepPlaceholder: false }),
      { wrapper: wrapWith(client) },
    );
    await waitFor(() => expect(fakeApi.getDashboard).toHaveBeenCalledWith("p1", "r1"));
  });
});

// Note: live grade SSE merging used to live here. It was deleted in the
// move to mutation-returns-result — the dismiss HTTP response now carries
// the rescored payload synchronously, and the dashboard refetches the
// accumulated rollup via refreshDashboard. See tests/api/test_routes_findings.py
// for the backend half of that contract.
