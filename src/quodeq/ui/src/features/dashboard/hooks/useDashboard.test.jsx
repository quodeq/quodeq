import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useDashboard } from "./useDashboard";
import { withQueryClient } from "../../../test-utils/withQueryClient.jsx";
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

  // The eval-completion path must actively refetch the always-mounted Overview
  // observer — otherwise a freshly-finished run leaves the Overview showing the
  // stale (often null) pre-run payload until the user switches projects.
  it("refreshDashboardActive refetches the mounted observer (eval-completion path)", async () => {
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

// Finding 5 (final whole-branch review): DashboardPage's projectInfo for a
// shared selection must come from the shared project's own info endpoint,
// not the local projects list (which can collide by id and bleed the local
// twin's stats/publishedBy into a shared Overview).
describe("useDashboard shared project info", () => {
  it("does not fetch sharedGetProjectInfo when selectedSource is 'local' (default)", async () => {
    const fakeApi = makeFakeApi();
    const { result } = renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: null }),
      { wrapper: ({ children }) => wrap(fakeApi, children) },
    );
    await waitFor(() => expect(result.current.dashboard).not.toBeNull());
    expect(fakeApi.sharedGetProjectInfo).not.toHaveBeenCalled();
    expect(result.current.sharedProjectInfo).toBeNull();
  });

  it("fetches sharedGetProjectInfo(projectId) and exposes it as sharedProjectInfo when selectedSource is 'shared'", async () => {
    const fakeApi = makeFakeApi();
    const { result } = renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: null, selectedSource: "shared" }),
      { wrapper: ({ children }) => wrap(fakeApi, children) },
    );
    await waitFor(() => expect(result.current.sharedProjectInfo).not.toBeNull());
    expect(fakeApi.sharedGetProjectInfo).toHaveBeenCalledWith("p1");
    expect(result.current.sharedProjectInfo.publishedBy).toBe("ana");
  });

  it("does not fetch sharedGetProjectInfo when there is no selected project", async () => {
    const fakeApi = makeFakeApi();
    renderHook(
      () => useDashboard({ selectedProject: "", selectedRun: null, selectedSource: "shared" }),
      { wrapper: ({ children }) => wrap(fakeApi, children) },
    );
    await new Promise((r) => setTimeout(r, 0));
    expect(fakeApi.sharedGetProjectInfo).not.toHaveBeenCalled();
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

  function wrapWith(client, fakeApi) {
    return ({ children }) => (
      <QueryClientProvider client={client}>
        <ApiProvider value={fakeApi}>{children}</ApiProvider>
      </QueryClientProvider>
    );
  }

  it("serves a cached completed run without any refetch", async () => {
    const fakeApi = makeFakeApi();
    const client = seededClient();
    const { result } = renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: "r1", keepPlaceholder: false }),
      { wrapper: wrapWith(client, fakeApi) },
    );
    await waitFor(() => expect(result.current.dashboard).not.toBeNull());
    expect(result.current.dashboard.marker).toBe("cached");
    // Give any errant background refetch a chance to fire, then assert quiet.
    await new Promise((r) => setTimeout(r, 50));
    expect(fakeApi.getDashboard).not.toHaveBeenCalled();
    expect(fakeApi.getProjectScores).not.toHaveBeenCalled();
  });

  it("still refetches a stale in-progress run", async () => {
    const fakeApi = makeFakeApi();
    const client = seededClient({ runStatus: "in_progress" });
    renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: "r1", keepPlaceholder: false }),
      { wrapper: wrapWith(client, fakeApi) },
    );
    await waitFor(() => expect(fakeApi.getDashboard).toHaveBeenCalledWith("p1", "r1"));
  });

  it("still refetches a stale latest selection", async () => {
    const fakeApi = makeFakeApi();
    const client = seededClient();
    client.setQueryData(
      projectKeys.dashboard("p1", null),
      { marker: "cached-latest", trend: [], dimensions: [] },
      { updatedAt: OLD() },
    );
    renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: null, keepPlaceholder: false }),
      { wrapper: wrapWith(client, fakeApi) },
    );
    await waitFor(() => expect(fakeApi.getDashboard).toHaveBeenCalledWith("p1", null));
  });

  it("refetches a frozen run after invalidation (dismiss/delete contract)", async () => {
    const fakeApi = makeFakeApi();
    const client = seededClient();
    await client.invalidateQueries({ queryKey: projectKeys.project("p1"), refetchType: "none" });
    renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: "r1", keepPlaceholder: false }),
      { wrapper: wrapWith(client, fakeApi) },
    );
    await waitFor(() => expect(fakeApi.getDashboard).toHaveBeenCalledWith("p1", "r1"));
  });

  // Run-detail flicker guard. The dashboard payload carries its OWN
  // cache-backed, dismiss-adjusted trend (post-#738, byte-identical to
  // scores.trend — see tests/services/test_scoring_parity.py). The scoped
  // scores query resolves a beat AFTER the dashboard query; folding scores.trend
  // in then would mint a new `dashboard` object identity. RunOverviewPanel
  // memoizes every derived value on the whole dashboard object and has a fade
  // animation, so a new identity re-renders the panel and replays the fade —
  // the visible "flicker". The hook must therefore keep the dashboard object
  // identity stable when the scores query resolves.
  it("keeps a stable dashboard identity when the scores query resolves (no run-detail flicker)", async () => {
    const fakeApi = makeFakeApi();
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 60_000 }, mutations: { retry: false } },
    });
    const dashTrend = [
      { runId: "r1", dimensionDetails: [{ dimension: "security", delta: 0.2, score: 7 }] },
    ];
    // Fresh + completed => frozen (staleTime Infinity), so no background
    // refetch swaps the object out from under us.
    client.setQueryData(
      projectKeys.dashboard("p1", "r1"),
      {
        marker: "dash",
        trend: dashTrend,
        dimensions: [{ dimension: "Security", overallScore: "7.0/10", violations: [], compliance: [] }],
        selectedRun: { runId: "r1", dateLabel: "2026-05-01" },
      },
      { updatedAt: Date.now() },
    );
    // Latest scores resolve first (its own distinct trend array) so the scoped
    // asOf can resolve to the completed r1.
    client.setQueryData(
      projectKeys.scores("p1", null),
      {
        accumulated: { score: 90 },
        trend: [{ runId: "r1", dimensionDetails: [{ dimension: "security", delta: 0.2, score: 7 }] }],
        availableRuns: [{ runId: "r1", status: "complete" }],
      },
      { updatedAt: Date.now() },
    );

    const { result } = renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: "r1", keepPlaceholder: false }),
      { wrapper: wrapWith(client, fakeApi) },
    );

    await waitFor(() => expect(result.current.dashboard?.marker).toBe("dash"));
    const before = result.current.dashboard;
    // Uses the dashboard payload's OWN trend, not the scores query's.
    expect(before.trend).toBe(dashTrend);

    // The scoped scores query resolves a beat later with its OWN trend array —
    // a different reference, identical values. Must not mint a new dashboard.
    await act(async () => {
      client.setQueryData(
        projectKeys.scores("p1", "r1"),
        {
          accumulated: { score: 90 },
          trend: [{ runId: "r1", dimensionDetails: [{ dimension: "security", delta: 0.2, score: 7 }] }],
        },
        { updatedAt: Date.now() },
      );
      await new Promise((r) => setTimeout(r, 0));
    });

    expect(result.current.dashboard).toBe(before); // identity stable => no flicker
    expect(result.current.dashboard.trend).toBe(dashTrend);
  });
});

// Note: live grade SSE merging used to live here. It was deleted in the
// move to mutation-returns-result — the dismiss HTTP response now carries
// the rescored payload synchronously, and the dashboard refetches the
// accumulated rollup via refreshDashboard. See tests/api/test_routes_findings.py
// for the backend half of that contract.
