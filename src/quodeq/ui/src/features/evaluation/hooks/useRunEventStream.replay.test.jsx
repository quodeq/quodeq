import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useRunEventStream } from "./useRunEventStream";
import { evaluationKeys, projectKeys } from "../../../api/queryKeys.js";
import { MockEventSource } from "../../../test-utils/MockEventSource.js";

function wrapperFor(client) {
  return function Wrapper({ children }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

describe("useRunEventStream (replayed runs and run-page freshness)", () => {
  beforeEach(() => {
    vi.stubGlobal('EventSource', MockEventSource);
    MockEventSource.last = null;
    MockEventSource.instances = [];
  });

  it("does not duplicate findings when the run's stream is reopened", () => {
    // A new connection replays the run from its first event. History opens
    // one per visit, so appending the replay onto the rows the last visit
    // left behind doubled the list every time, up to the cap.
    const client = new QueryClient();
    const wrapper = wrapperFor(client);
    const replay = () => act(() => {
      MockEventSource.last.emit("finding", { id: 1, practice_id: "P1" });
      MockEventSource.last.emit("finding", { id: 2, practice_id: "P2" });
    });
    const first = renderHook(() => useRunEventStream("job-1"), { wrapper });
    replay();
    first.unmount();
    renderHook(() => useRunEventStream("job-1"), { wrapper });
    expect(MockEventSource.instances).toHaveLength(2);
    replay();
    expect(client.getQueryData(evaluationKeys.findings("job-1")).map((f) => f.id)).toEqual([1, 2]);
  });

  it("keeps the held rows in place when a finding lands on a full cache", () => {
    // Dropping the oldest row on every event shifts all the others by one,
    // and the cache then deep-compares each of them against its neighbour:
    // milliseconds per finding, seconds for a replayed run.
    const client = new QueryClient();
    renderHook(() => useRunEventStream("job-1"), { wrapper: wrapperFor(client) });
    const key = evaluationKeys.findings("job-1");
    act(() => MockEventSource.last.emit("finding", { id: 0, practice_id: "P" }));
    client.setQueryData(key, (prev) => [
      ...prev, ...Array.from({ length: 4999 }, (_, i) => ({ id: i + 1, practice_id: "P" })),
    ]);
    const before = client.getQueryData(key);
    act(() => MockEventSource.last.emit("finding", { id: 5000, practice_id: "P" }));
    const after = client.getQueryData(key);
    expect(after[0]).toBe(before[0]);
    expect(after[4999]).toBe(before[4999]);
    expect(after.at(-1).id).toBe(5000);
  });

  it("trims the oldest findings in one block once the cache overshoots its cap", () => {
    const client = new QueryClient();
    renderHook(() => useRunEventStream("job-1"), { wrapper: wrapperFor(client) });
    const key = evaluationKeys.findings("job-1");
    act(() => MockEventSource.last.emit("finding", { id: 0, practice_id: "P" }));
    client.setQueryData(key, (prev) => [
      ...prev, ...Array.from({ length: 5999 }, (_, i) => ({ id: i + 1, practice_id: "P" })),
    ]);
    act(() => MockEventSource.last.emit("finding", { id: 6000, practice_id: "P" }));
    const after = client.getQueryData(key);
    expect(after).toHaveLength(5000);
    expect(after.at(-1).id).toBe(6000);
    expect(after[0].id).toBe(1001);
  });

  // The run page of a still-running run reads project-scoped queries that
  // nothing else refreshes mid-run: a finished dimension has to mark them
  // stale, or the page keeps the dimensions it was opened with.
  it.each([
    ["the job's output run", "job-1", { outputProject: "proj", outputRunId: "run-1" }],
    ["the run id History subscribes with", "run-1", null],
  ])("marks the run's project queries stale when a dimension completes (%s)", (_label, jobId, cachedJob) => {
    const client = new QueryClient();
    const wrapper = wrapperFor(client);
    if (cachedJob) client.setQueryData(evaluationKeys.status(jobId), { jobId, status: "running", ...cachedJob });
    const runDashboard = projectKeys.dashboard("proj", "run-1");
    const runScores = projectKeys.runScores("proj", "run-1");
    const otherRun = projectKeys.dashboard("proj", "run-0");
    const latestScores = projectKeys.scores("proj", null);
    for (const key of [runDashboard, runScores, otherRun, latestScores]) client.setQueryData(key, {});
    renderHook(() => useRunEventStream(jobId), { wrapper });
    act(() => MockEventSource.last.emit("dimension-completed", { dimension: "security", score: 90 }));
    const invalidated = (key) => client.getQueryState(key).isInvalidated;
    expect(invalidated(runDashboard)).toBe(true);
    expect(invalidated(runScores)).toBe(true);
    expect(invalidated(otherRun)).toBe(false);
    expect(invalidated(latestScores)).toBe(false);
  });
});
