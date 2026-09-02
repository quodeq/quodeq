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

// Split from useDashboard.test.jsx: dashboard-object-identity stability
// when the scores query resolves (run-detail flicker guard), and
// placeholder-data scope on project/run switches.

describe("useDashboard frozen historical runs", () => {
  function wrapWith(client, fakeApi) {
    return ({ children }) => (
      <QueryClientProvider client={client}>
        <ApiProvider value={fakeApi}>{children}</ApiProvider>
      </QueryClientProvider>
    );
  }

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

  // Fallback path: older cached payloads / the grade-formula early-return path
  // carry no trend of their own, so the hook folds in scores.trend. That must
  // not reintroduce the flicker: a new (but equivalent) scores object whose
  // trend array is the SAME reference must not mint a new dashboard identity.
  it("keeps a stable dashboard identity in the fallback path when the trend reference is unchanged", async () => {
    const fakeApi = makeFakeApi();
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 60_000 }, mutations: { retry: false } },
    });
    const sharedTrend = [
      { runId: "r1", dimensionDetails: [{ dimension: "security", delta: 0.2, score: 7 }] },
    ];
    // No trend on the payload itself => fallback path.
    client.setQueryData(
      projectKeys.dashboard("p1", "r1"),
      {
        marker: "dash",
        trend: [],
        dimensions: [{ dimension: "Security", overallScore: "7.0/10", violations: [], compliance: [] }],
        selectedRun: { runId: "r1", dateLabel: "2026-05-01" },
      },
      { updatedAt: Date.now() },
    );
    client.setQueryData(
      projectKeys.scores("p1", null),
      {
        accumulated: { score: 90 },
        trend: sharedTrend,
        availableRuns: [{ runId: "r1", status: "complete" }],
      },
      { updatedAt: Date.now() },
    );
    // Pre-seed the scoped query too (same reference), so the initial mount
    // is already resolved and doesn't race the fakeApi mock's own fetch.
    client.setQueryData(
      projectKeys.scores("p1", "r1"),
      { accumulated: { score: 90 }, trend: sharedTrend },
      { updatedAt: Date.now() },
    );

    const { result } = renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: "r1", keepPlaceholder: false }),
      { wrapper: wrapWith(client, fakeApi) },
    );

    await waitFor(() => expect(result.current.dashboard?.marker).toBe("dash"));
    const before = result.current.dashboard;
    expect(before.trend).toBe(sharedTrend);

    // The scoped scores query resolves a beat later with a DIFFERENT scores
    // object, but the SAME trend array reference. Must not mint a new dashboard.
    await act(async () => {
      client.setQueryData(
        projectKeys.scores("p1", "r1"),
        { accumulated: { score: 90 }, trend: sharedTrend },
        { updatedAt: Date.now() },
      );
      await new Promise((r) => setTimeout(r, 0));
    });

    expect(result.current.dashboard).toBe(before);
    expect(result.current.dashboard.trend).toBe(sharedTrend);

    // Now the trend reference genuinely changes: the data must flow.
    const newTrend = [
      { runId: "r1", dimensionDetails: [{ dimension: "security", delta: 0.5, score: 8 }] },
    ];
    await act(async () => {
      client.setQueryData(
        projectKeys.scores("p1", "r1"),
        { accumulated: { score: 90 }, trend: newTrend },
        { updatedAt: Date.now() },
      );
      await new Promise((r) => setTimeout(r, 0));
    });

    expect(result.current.dashboard).not.toBe(before);
    expect(result.current.dashboard.trend[0].dimensionDetails[0].delta).toBe(0.5);
  });

  // placeholderData is observer-scoped, not key-scoped — an unguarded
  // (prev) => prev parks the PREVIOUS project's overview on screen (with
  // loading false, so no loading state either) until the new project's fetch
  // lands. See samePlaceholderScope in api/queryKeys.js.
  //
  // NOTE: these tests must NOT use `wrap()` above — it remounts the subtree on
  // every render and destroys the observer that carries the placeholder, so
  // they would pass against the bug. See withStableQueryApi's doc comment.
  describe("placeholder scope", () => {
    const stableWrapper = withStableQueryApi;

    it("drops the previous project's dashboard while the new project loads", async () => {
      let release;
      const fakeApi = makeFakeApi();
      fakeApi.getDashboard = vi.fn(async (project, run) => {
        if (project === "p1") return makeDashboardPayload({ project, run: run || "latest" });
        return new Promise((resolve) => {
          release = () => resolve(makeDashboardPayload({ project, summary: { score: 20 } }));
        });
      });
      const { result, rerender } = renderHook(
        ({ p }) => useDashboard({ selectedProject: p, selectedRun: null }),
        { wrapper: stableWrapper(fakeApi), initialProps: { p: "p1" } },
      );
      await waitFor(() => expect(result.current.dashboard?.summary?.score).toBe(75));

      rerender({ p: "p2" });
      // No stale overview, and the page gets a real loading state to render.
      expect(result.current.dashboard).toBeNull();
      expect(result.current.loading).toBe(true);

      release();
      await waitFor(() => expect(result.current.dashboard?.summary?.score).toBe(20));
    });

    it("keeps the previous run's dashboard while a new run in the SAME project loads", async () => {
      let release;
      const fakeApi = makeFakeApi();
      fakeApi.getDashboard = vi.fn(async (project, run) => {
        if (!run || run === "latest") return makeDashboardPayload({ project, run: "latest" });
        return new Promise((resolve) => {
          release = () => resolve(makeDashboardPayload({ project, run, summary: { score: 33 } }));
        });
      });
      const { result, rerender } = renderHook(
        ({ run }) => useDashboard({ selectedProject: "p1", selectedRun: run }),
        { wrapper: stableWrapper(fakeApi), initialProps: { run: null } },
      );
      await waitFor(() => expect(result.current.dashboard?.summary?.score).toBe(75));

      rerender({ run: "r_old" });
      await waitFor(() => expect(fakeApi.getDashboard).toHaveBeenCalledWith("p1", "r_old"));
      // Instant perceived navigation within a project is preserved.
      expect(result.current.dashboard?.summary?.score).toBe(75);

      release();
      await waitFor(() => expect(result.current.dashboard?.summary?.score).toBe(33));
    });
  });
});
