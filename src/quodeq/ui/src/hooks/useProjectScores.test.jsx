import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useProjectScores } from "./useProjectScores";
import { withQueryClient } from "../test-utils/withQueryClient.jsx";
import { getProjectScores } from "../api/index.js";
import { projectKeys } from "../api/queryKeys.js";

vi.mock("../api/index.js", () => ({
  getProjectScores: vi.fn(async (project, asOf) => {
    if (asOf) {
      return {
        accumulated: { score: 80 },
        trend: [{ runId: asOf }],
        availableRuns: [
          { runId: "r9", status: "complete" },
          { runId: "r1", status: "complete" },
        ],
      };
    }
    return {
      accumulated: { score: 90 },
      trend: [],
      availableRuns: [
        { runId: "r9", status: "complete" },
        { runId: "r1", status: "complete" },
      ],
    };
  }),
}));

beforeEach(() => {
  getProjectScores.mockClear();
});

describe("useProjectScores", () => {
  it("returns null when project is empty", () => {
    const { result } = renderHook(
      () => useProjectScores({ selectedProject: "", selectedRun: null }),
      { wrapper: withQueryClient() },
    );
    expect(result.current.scores).toBeNull();
    expect(result.current.latestScores).toBeNull();
  });

  it("fetches scores for the selected run + latest in parallel", async () => {
    const { result } = renderHook(
      () => useProjectScores({ selectedProject: "p1", selectedRun: "r9" }),
      { wrapper: withQueryClient() },
    );
    await waitFor(() => {
      expect(result.current.scores?.accumulated?.score).toBe(80);
      expect(result.current.latestScores?.accumulated?.score).toBe(90);
    });
  });

  it("derives availableRuns from the scores payload", async () => {
    const { result } = renderHook(
      () => useProjectScores({ selectedProject: "p1", selectedRun: null }),
      { wrapper: withQueryClient() },
    );
    await waitFor(() => {
      expect(result.current.availableRuns.map((r) => r.runId)).toEqual(["r9", "r1"]);
    });
  });

  it("falls back to latest when selectedRun points at an in_progress run", async () => {
    // Latest query returns availableRuns marking r_running as in_progress; the
    // scoped query should NOT request asOf=r_running (would leak partial dims
    // into Overview while the eval is alive). It re-uses the latest payload.
    getProjectScores.mockImplementation(async (project, asOf) => ({
      accumulated: { score: asOf ? 80 : 90 },
      trend: [],
      availableRuns: [
        { runId: "r_running", status: "in_progress" },
        { runId: "r_done", status: "complete" },
      ],
    }));
    const { result } = renderHook(
      () => useProjectScores({ selectedProject: "p1", selectedRun: "r_running" }),
      { wrapper: withQueryClient() },
    );
    await waitFor(() => {
      expect(result.current.scores?.accumulated?.score).toBe(90);
    });
    // Confirm the scoped call was never issued with asOf=r_running.
    const asOfArgs = getProjectScores.mock.calls.map((c) => c[1]);
    expect(asOfArgs).not.toContain("r_running");
  });

  it("falls back to latest when selectedRun is unknown (not in availableRuns)", async () => {
    getProjectScores.mockImplementation(async (project, asOf) => ({
      accumulated: { score: asOf ? 80 : 90 },
      trend: [],
      availableRuns: [{ runId: "r_done", status: "complete" }],
    }));
    const { result } = renderHook(
      () => useProjectScores({ selectedProject: "p1", selectedRun: "r_ghost" }),
      { wrapper: withQueryClient() },
    );
    await waitFor(() => {
      expect(result.current.scores?.accumulated?.score).toBe(90);
    });
    const asOfArgs = getProjectScores.mock.calls.map((c) => c[1]);
    expect(asOfArgs).not.toContain("r_ghost");
  });

  it("still scopes the query when selectedRun is a known completed run", async () => {
    getProjectScores.mockImplementation(async (project, asOf) => ({
      accumulated: { score: asOf ? 80 : 90 },
      trend: [],
      availableRuns: [
        { runId: "r_done", status: "complete" },
        { runId: "r_old", status: "complete" },
      ],
    }));
    const { result } = renderHook(
      () => useProjectScores({ selectedProject: "p1", selectedRun: "r_old" }),
      { wrapper: withQueryClient() },
    );
    await waitFor(() => {
      expect(result.current.scores?.accumulated?.score).toBe(80);
    });
    const asOfArgs = getProjectScores.mock.calls.map((c) => c[1]);
    expect(asOfArgs).toContain("r_old");
  });

  // As-of scores for a completed run are immutable apart from explicit
  // mutations (which invalidate the project subtree), so a cached entry
  // must be served without a background refetch — no dim flash on re-entry.
  it("serves cached as-of scores for a completed run without refetching", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 60_000 } },
    });
    client.setQueryData(
      projectKeys.scores("p1", null),
      { accumulated: { score: 90 }, trend: [], availableRuns: [{ runId: "r1", status: "complete" }] },
      { updatedAt: Date.now() },
    );
    client.setQueryData(
      projectKeys.scores("p1", "r1"),
      { accumulated: { score: 80 }, trend: [] },
      { updatedAt: Date.now() - 120_000 }, // well past the old 60s staleTime
    );
    const { result } = renderHook(
      () => useProjectScores({ selectedProject: "p1", selectedRun: "r1", keepPlaceholder: false }),
      { wrapper: ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider> },
    );
    await waitFor(() => expect(result.current.scores?.accumulated?.score).toBe(80));
    await new Promise((r) => setTimeout(r, 50));
    expect(getProjectScores).not.toHaveBeenCalled();
  });

});
