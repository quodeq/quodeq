import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { useDashboard } from "./useDashboard";
import { withQueryClient } from "../../../test-utils/withQueryClient.jsx";
import { ApiProvider } from "../../../api/ApiContext.jsx";
import { MockEventSource } from "../../../test-utils/MockEventSource.js";

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
});

describe("useDashboard — live grades (VITE_USE_LIVE_GRADES=true)", () => {
  let originalEventSource;
  let originalFlag;

  beforeEach(() => {
    originalEventSource = global.EventSource;
    originalFlag = import.meta.env.VITE_USE_LIVE_GRADES;
    MockEventSource.last = null;
    global.EventSource = MockEventSource;
    import.meta.env.VITE_USE_LIVE_GRADES = "true";
  });

  afterEach(() => {
    global.EventSource = originalEventSource;
    import.meta.env.VITE_USE_LIVE_GRADES = originalFlag;
  });

  it("subscribes to useGradeStream once the dashboard runId is known", async () => {
    const { result } = renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: "r1" }),
      { wrapper: ({ children }) => wrap(children) },
    );
    // Wait for the dashboard fetch to resolve so runId is known.
    await waitFor(() => expect(result.current.dashboard).not.toBeNull());
    expect(MockEventSource.last).not.toBeNull();
    expect(MockEventSource.last.url).toBe("/api/evaluations/r1/events");
  });

  it("does not subscribe when flag is off", async () => {
    import.meta.env.VITE_USE_LIVE_GRADES = "false";
    const { result } = renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: "r1" }),
      { wrapper: ({ children }) => wrap(children) },
    );
    await waitFor(() => expect(result.current.dashboard).not.toBeNull());
    expect(MockEventSource.last).toBeNull();
  });

  it("updates dashboard.dimensions grades when scores.updated SSE arrives", async () => {
    const { result } = renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: "r1" }),
      { wrapper: ({ children }) => wrap(children) },
    );
    await waitFor(() => expect(result.current.dashboard).not.toBeNull());

    const payload = {
      dimensions: [
        { dimension: "Security", overallScore: "9.0/10", overallGrade: "A" },
      ],
      summary: { overallGrade: "A", numericAverage: 9.0 },
    };

    act(() => {
      MockEventSource.last.emit("scores.updated", payload);
    });

    await waitFor(() => {
      const sec = result.current.dashboard.dimensions.find((d) => d.dimension === "Security");
      expect(sec?.overallGrade).toBe("A");
      expect(sec?.overallScore).toBe("9.0/10");
    });
  });

  it("preserves violations list when SSE patches grades", async () => {
    fakeApi.getDashboard.mockImplementationOnce(async () => ({
      project: "p1",
      run: "r1",
      trend: [],
      summary: { score: 75 },
      dimensions: [
        {
          dimension: "Security",
          overallScore: "7.0/10",
          overallGrade: "B",
          violations: [{ file: "a.py", line: 1, severity: "major", reason: "bad" }],
          compliance: [],
          principles: [],
        },
      ],
      selectedRun: { runId: "r1", dateLabel: "2026-05-01" },
    }));

    const { result } = renderHook(
      () => useDashboard({ selectedProject: "p1", selectedRun: "r1" }),
      { wrapper: ({ children }) => wrap(children) },
    );
    await waitFor(() => expect(result.current.dashboard).not.toBeNull());

    act(() => {
      MockEventSource.last.emit("scores.updated", {
        dimensions: [{ dimension: "Security", overallScore: "8.5/10", overallGrade: "B+" }],
        summary: { overallGrade: "B+", numericAverage: 8.5 },
      });
    });

    await waitFor(() => {
      const sec = result.current.dashboard.dimensions.find((d) => d.dimension === "Security");
      expect(sec?.overallGrade).toBe("B+");
      // violations list must survive the SSE patch
      expect(sec?.violations?.length).toBe(1);
    });
  });
});
