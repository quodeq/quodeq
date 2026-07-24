import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useProjectScores } from "./useProjectScores";
import { withQueryClient } from "../test-utils/withQueryClient.jsx";
import { ApiProvider } from "../api/ApiContext.jsx";
import { projectKeys } from "../api/queryKeys.js";

function makeFakeApi() {
  return {
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
    sharedGetProjectScores: vi.fn(async (project, asOf) => ({
      accumulated: { score: 55 },
      trend: [],
      availableRuns: [{ runId: "r1", status: "complete" }],
    })),
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

describe("useProjectScores", () => {
  let fakeApi;

  beforeEach(() => {
    fakeApi = makeFakeApi();
  });

  it("returns null when project is empty", () => {
    const { result } = renderHook(
      () => useProjectScores({ selectedProject: "", selectedRun: null }),
      { wrapper: ({ children }) => wrap(fakeApi, children) },
    );
    expect(result.current.scores).toBeNull();
    expect(result.current.latestScores).toBeNull();
  });

  it("fetches scores for the selected run + latest in parallel", async () => {
    const { result } = renderHook(
      () => useProjectScores({ selectedProject: "p1", selectedRun: "r9" }),
      { wrapper: ({ children }) => wrap(fakeApi, children) },
    );
    await waitFor(() => {
      expect(result.current.scores?.accumulated?.score).toBe(80);
      expect(result.current.latestScores?.accumulated?.score).toBe(90);
    });
  });

  it("derives availableRuns from the scores payload", async () => {
    const { result } = renderHook(
      () => useProjectScores({ selectedProject: "p1", selectedRun: null }),
      { wrapper: ({ children }) => wrap(fakeApi, children) },
    );
    await waitFor(() => {
      expect(result.current.availableRuns.map((r) => r.runId)).toEqual(["r9", "r1"]);
    });
  });

  it("falls back to latest when selectedRun points at an in_progress run", async () => {
    // Latest query returns availableRuns marking r_running as in_progress; the
    // scoped query should NOT request asOf=r_running (would leak partial dims
    // into Overview while the eval is alive). It re-uses the latest payload.
    fakeApi.getProjectScores.mockImplementation(async (project, asOf) => ({
      accumulated: { score: asOf ? 80 : 90 },
      trend: [],
      availableRuns: [
        { runId: "r_running", status: "in_progress" },
        { runId: "r_done", status: "complete" },
      ],
    }));
    const { result } = renderHook(
      () => useProjectScores({ selectedProject: "p1", selectedRun: "r_running" }),
      { wrapper: ({ children }) => wrap(fakeApi, children) },
    );
    await waitFor(() => {
      expect(result.current.scores?.accumulated?.score).toBe(90);
    });
    // Confirm the scoped call was never issued with asOf=r_running.
    const asOfArgs = fakeApi.getProjectScores.mock.calls.map((c) => c[1]);
    expect(asOfArgs).not.toContain("r_running");
  });

  it("falls back to latest when selectedRun is unknown (not in availableRuns)", async () => {
    fakeApi.getProjectScores.mockImplementation(async (project, asOf) => ({
      accumulated: { score: asOf ? 80 : 90 },
      trend: [],
      availableRuns: [{ runId: "r_done", status: "complete" }],
    }));
    const { result } = renderHook(
      () => useProjectScores({ selectedProject: "p1", selectedRun: "r_ghost" }),
      { wrapper: ({ children }) => wrap(fakeApi, children) },
    );
    await waitFor(() => {
      expect(result.current.scores?.accumulated?.score).toBe(90);
    });
    const asOfArgs = fakeApi.getProjectScores.mock.calls.map((c) => c[1]);
    expect(asOfArgs).not.toContain("r_ghost");
  });

  it("still scopes the query when selectedRun is a known completed run", async () => {
    fakeApi.getProjectScores.mockImplementation(async (project, asOf) => ({
      accumulated: { score: asOf ? 80 : 90 },
      trend: [],
      availableRuns: [
        { runId: "r_done", status: "complete" },
        { runId: "r_old", status: "complete" },
      ],
    }));
    const { result } = renderHook(
      () => useProjectScores({ selectedProject: "p1", selectedRun: "r_old" }),
      { wrapper: ({ children }) => wrap(fakeApi, children) },
    );
    await waitFor(() => {
      expect(result.current.scores?.accumulated?.score).toBe(80);
    });
    const asOfArgs = fakeApi.getProjectScores.mock.calls.map((c) => c[1]);
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
      {
        wrapper: ({ children }) => (
          <QueryClientProvider client={client}>
            <ApiProvider value={fakeApi}>{children}</ApiProvider>
          </QueryClientProvider>
        ),
      },
    );
    await waitFor(() => expect(result.current.scores?.accumulated?.score).toBe(80));
    await new Promise((r) => setTimeout(r, 50));
    expect(fakeApi.getProjectScores).not.toHaveBeenCalled();
  });

  // placeholderData is observer-scoped, not key-scoped: without a guard it
  // hands back whatever this observer last saw, so switching PROJECTS keeps
  // the previous project's scores on screen (and suppresses `loading`) until
  // the new fetch lands.
  //
  // NOTE: these tests must NOT use `wrap()` above. It calls withQueryClient()
  // during the wrapper's render, minting a fresh component type every render —
  // React then remounts the whole subtree, destroying the very observer that
  // carries placeholderData across a key change. Build the wrapper ONCE.
  describe("placeholder scope", () => {
    function stableWrapper(api) {
      const QC = withQueryClient();
      return function Wrapper({ children }) {
        return (
          <QC>
            <ApiProvider value={api}>{children}</ApiProvider>
          </QC>
        );
      };
    }

    it("drops the previous project's scores while the new project loads", async () => {
      let release;
      const api = {
        getProjectScores: vi.fn(async (project) => {
          if (project === "p1") {
            return { accumulated: { score: 90 }, trend: [], availableRuns: [{ runId: "r9", status: "complete" }] };
          }
          return new Promise((resolve) => {
            release = () => resolve({ accumulated: { score: 40 }, trend: [], availableRuns: [] });
          });
        }),
        sharedGetProjectScores: vi.fn(),
      };
      const { result, rerender } = renderHook(
        ({ p }) => useProjectScores({ selectedProject: p, selectedRun: null }),
        { wrapper: stableWrapper(api), initialProps: { p: "p1" } },
      );
      await waitFor(() => expect(result.current.latestScores?.accumulated?.score).toBe(90));

      rerender({ p: "p2" });
      expect(result.current.latestScores).toBeNull();
      expect(result.current.scores).toBeNull();
      expect(result.current.loading).toBe(true);

      release();
      await waitFor(() => expect(result.current.latestScores?.accumulated?.score).toBe(40));
    });

    it("keeps the previous run's scores while a new run in the SAME project loads", async () => {
      let release;
      const api = {
        getProjectScores: vi.fn(async (project, asOf) => {
          if (!asOf) {
            return {
              accumulated: { score: 90 },
              trend: [],
              availableRuns: [
                { runId: "r9", status: "complete" },
                { runId: "r1", status: "complete" },
              ],
            };
          }
          return new Promise((resolve) => {
            release = () => resolve({ accumulated: { score: 80 }, trend: [] });
          });
        }),
        sharedGetProjectScores: vi.fn(),
      };
      const { result, rerender } = renderHook(
        ({ run }) => useProjectScores({ selectedProject: "p1", selectedRun: run }),
        { wrapper: stableWrapper(api), initialProps: { run: null } },
      );
      await waitFor(() => expect(result.current.scores?.accumulated?.score).toBe(90));

      rerender({ run: "r1" });
      await waitFor(() => expect(api.getProjectScores).toHaveBeenCalledWith("p1", "r1"));
      // Same project — the previous run's payload stays visible during the fetch.
      expect(result.current.scores?.accumulated?.score).toBe(90);

      release();
      await waitFor(() => expect(result.current.scores?.accumulated?.score).toBe(80));
    });

    it("drops the placeholder when only the SOURCE changes", async () => {
      let release;
      const api = {
        getProjectScores: vi.fn(async () => ({ accumulated: { score: 90 }, trend: [], availableRuns: [] })),
        sharedGetProjectScores: vi.fn(
          async () => new Promise((resolve) => {
            release = () => resolve({ accumulated: { score: 55 }, trend: [], availableRuns: [] });
          }),
        ),
      };
      const { result, rerender } = renderHook(
        ({ source }) => useProjectScores({ selectedProject: "p1", selectedRun: null, selectedSource: source }),
        { wrapper: stableWrapper(api), initialProps: { source: "local" } },
      );
      await waitFor(() => expect(result.current.latestScores?.accumulated?.score).toBe(90));

      rerender({ source: "shared" });
      expect(result.current.latestScores).toBeNull();
      expect(result.current.loading).toBe(true);

      release();
      await waitFor(() => expect(result.current.latestScores?.accumulated?.score).toBe(55));
    });
  });

  // Task 17: source-aware fetch selection. A shared-source selection must
  // read from the shared-repo mirror endpoints, never the local ones.
  describe("source-aware fetch selection", () => {
    it("calls getProjectScores (not sharedGetProjectScores) when selectedSource is 'local' (default)", async () => {
      const { result } = renderHook(
        () => useProjectScores({ selectedProject: "p1", selectedRun: null }),
        { wrapper: ({ children }) => wrap(fakeApi, children) },
      );
      await waitFor(() => expect(result.current.latestScores).not.toBeNull());
      expect(fakeApi.getProjectScores).toHaveBeenCalled();
      expect(fakeApi.sharedGetProjectScores).not.toHaveBeenCalled();
    });

    it("calls sharedGetProjectScores (not getProjectScores) when selectedSource is 'shared'", async () => {
      const { result } = renderHook(
        () => useProjectScores({ selectedProject: "p1", selectedRun: null, selectedSource: "shared" }),
        { wrapper: ({ children }) => wrap(fakeApi, children) },
      );
      await waitFor(() => expect(result.current.latestScores?.accumulated?.score).toBe(55));
      expect(fakeApi.sharedGetProjectScores).toHaveBeenCalled();
      expect(fakeApi.getProjectScores).not.toHaveBeenCalled();
    });
  });
});
