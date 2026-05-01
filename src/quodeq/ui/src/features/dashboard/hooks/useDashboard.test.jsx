import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { useDashboard } from "./useDashboard";
import { withQueryClient } from "../../../test-utils/withQueryClient.jsx";
import { ApiProvider } from "../../../api/ApiContext.jsx";

const fakeApi = {
  getDashboard: vi.fn(async (project, run) => ({
    project,
    run: run || "latest",
    trend: [],
    summary: { score: 75 },
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
});
