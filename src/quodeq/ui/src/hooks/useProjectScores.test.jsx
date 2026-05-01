import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useProjectScores } from "./useProjectScores";
import { withQueryClient } from "../test-utils/withQueryClient.jsx";

vi.mock("../api/index.js", () => ({
  getProjectScores: vi.fn(async (project, asOf) => {
    if (asOf) {
      return {
        accumulated: { score: 80 },
        trend: [{ runId: asOf }],
        availableRuns: [],
      };
    }
    return {
      accumulated: { score: 90 },
      trend: [],
      availableRuns: [{ runId: "r1" }],
    };
  }),
}));

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
      expect(result.current.availableRuns).toEqual([{ runId: "r1" }]);
    });
  });
});
