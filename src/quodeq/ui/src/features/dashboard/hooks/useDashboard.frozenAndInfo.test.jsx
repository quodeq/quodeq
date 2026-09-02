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

// Split from useDashboard.test.jsx: shared-project-info fetching, the
// frozen-historical-run cache/refetch core, and the scoring-metadata
// whitelist.

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
});

describe("useDashboard — scoring metadata crosses the whitelist", () => {
  it("exposes customFormula from the scores payload", async () => {
    const fakeApi = makeFakeApi();
    fakeApi.getProjectScores = vi.fn(async () => ({
      accumulated: { score: 90 }, trend: [], availableRuns: [],
      scoring: { customFormula: true },
    }));
    const { result } = renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: null }),
      { wrapper: withStableQueryApi(fakeApi) },
    );
    await waitFor(() => expect(result.current.customFormula).toBe(true));
  });

  it("defaults to false when the payload omits it", async () => {
    const fakeApi = makeFakeApi();
    const { result } = renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: null }),
      { wrapper: withStableQueryApi(fakeApi) },
    );
    await waitFor(() => expect(result.current.accumulated).toBeTruthy());
    expect(result.current.customFormula).toBe(false);
  });
});
