import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useProjectScores } from "./useProjectScores";
import { withStableQueryApi } from "../test-utils/withQueryClient.jsx";

describe("useProjectScores", () => {
  // placeholderData is observer-scoped, not key-scoped: without a guard it
  // hands back whatever this observer last saw, so switching PROJECTS keeps
  // the previous project's scores on screen (and suppresses `loading`) until
  // the new fetch lands.
  //
  // NOTE: these tests must NOT use `wrap()` above — it remounts the subtree on
  // every render and destroys the observer that carries placeholderData, so
  // they would pass against the bug. See withStableQueryApi's doc comment.
  describe("placeholder scope", () => {
    const stableWrapper = withStableQueryApi;

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

  // Selecting a day on the score-history chart refetches as-of scores, and
  // placeholderData keeps the PREVIOUS day's numbers on screen meanwhile.
  // scoresPending is what lets the dimension cards say so instead of
  // presenting stale grades as settled.
  describe("scoresPending", () => {
    // Must use withStableQueryApi: a wrapper rebuilt per render remounts the
    // subtree and destroys isPlaceholderData, so this would pass either way.
    it("is true while a newly-selected run is in flight, false once it lands", async () => {
      let release;
      const gate = new Promise((r) => { release = r; });
      let call = 0;
      const api = {
        getProjectScores: vi.fn(async (project, asOf) => {
          call += 1;
          if (call > 1 && asOf) await gate;
          return {
            accumulated: { score: asOf ? 80 : 90 },
            trend: [],
            availableRuns: [
              { runId: "r9", status: "complete" },
              { runId: "r1", status: "complete" },
            ],
          };
        }),
        sharedGetProjectScores: vi.fn(),
      };

      const { result, rerender } = renderHook(
        ({ run }) => useProjectScores({ selectedProject: "p1", selectedRun: run }),
        { wrapper: withStableQueryApi(api), initialProps: { run: null } },
      );
      await waitFor(() => expect(result.current.scores?.accumulated?.score).toBe(90));
      expect(result.current.scoresPending).toBe(false);

      rerender({ run: "r1" });
      await waitFor(() => expect(result.current.scoresPending).toBe(true));
      // The old day's scores are still what's rendered — that is the point.
      expect(result.current.scores?.accumulated?.score).toBe(90);

      release();
      await waitFor(() => expect(result.current.scores?.accumulated?.score).toBe(80));
      expect(result.current.scoresPending).toBe(false);
    });
  });
});
