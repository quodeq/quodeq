import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useQuery, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useRunEventStream } from "./useRunEventStream";
import { STREAM_STATE } from "./runEventSourceRegistry.js";
import { evaluationKeys, projectKeys } from "../../../api/queryKeys.js";
import { withQueryClient } from "../../../test-utils/withQueryClient.jsx";
import { MockEventSource } from "../../../test-utils/MockEventSource.js";

function renderStreamWithSpy(jobId) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  const invalidateSpy = vi.spyOn(client, "invalidateQueries");
  function Wrapper({ children }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }
  const utils = renderHook(() => useRunEventStream(jobId), { wrapper: Wrapper });
  return { ...utils, invalidateSpy, client };
}

function renderStreamAndQuery(jobId, key) {
  const wrapper = withQueryClient();
  return renderHook(
    () => {
      useRunEventStream(jobId);
      return useQuery({
        queryKey: key,
        queryFn: () => null,
        enabled: !!jobId,
      });
    },
    { wrapper },
  );
}

describe("useRunEventStream (cache-writer)", () => {
  beforeEach(() => {
    vi.stubGlobal('EventSource', MockEventSource);
    MockEventSource.last = null;
    MockEventSource.instances = [];
  });

  it("opens an EventSource against the events endpoint", () => {
    renderStreamAndQuery("job-123", evaluationKeys.status("job-123"));
    expect(MockEventSource.last.url).toBe("/api/evaluations/job-123/events");
  });

  it("normalises a raw status frame into the Job shape in evaluationKeys.status", async () => {
    // The frame is status.json verbatim: snake_case, and `state` is a
    // RunState. Readers expect the REST Job (camelCase, `status`), so writing
    // the frame raw left `job.status` undefined and the status pill fell
    // through to "cancelled" on a running job.
    const { result } = renderStreamAndQuery("job-1", evaluationKeys.status("job-1"));
    act(() => {
      MockEventSource.last.emit("status", {
        state: "running", job_id: "job-1", phase: "analyzing",
        current_dimension: "security", started_at: "2025-01-01T00:00:00Z",
        dimensions: ["security"], time_limit_s: 600,
      });
    });
    await waitFor(() => expect(result.current.data?.status).toBe("running"));
    expect(result.current.data).toMatchObject({
      jobId: "job-1", phase: "analyzing", currentDimension: "security",
      startedAt: "2025-01-01T00:00:00Z", dimensions: ["security"], timeLimitS: 600,
    });
    expect(result.current.data.state).toBeUndefined();
  });

  it("maps the pending and finalizing run states onto a running job", async () => {
    const { result } = renderStreamAndQuery("job-1", evaluationKeys.status("job-1"));
    act(() => MockEventSource.last.emit("status", { state: "pending" }));
    await waitFor(() => expect(result.current.data?.status).toBe("running"));
    act(() => MockEventSource.last.emit("status", { state: "finalizing" }));
    await waitFor(() => expect(result.current.data?.status).toBe("running"));
  });

  it("keeps REST-only job fields when a status frame lands on a cached job", async () => {
    const { client } = renderStreamWithSpy("job-1");
    // A previous REST fetch populated the slot with the full Job.
    client.setQueryData(evaluationKeys.status("job-1"), {
      jobId: "job-1", status: "running", currentDimension: "security",
      outputProject: "proj", outputRunId: "run-1", source: "external",
    });
    act(() => {
      MockEventSource.last.emit("status", { state: "done", current_dimension: null });
    });
    const job = client.getQueryData(evaluationKeys.status("job-1"));
    // The frame wins for what it knows, including a field the run cleared.
    expect(job).toMatchObject({
      status: "done", currentDimension: null,
      outputProject: "proj", outputRunId: "run-1", source: "external",
    });
  });

  it("appends finding events into evaluationKeys.findings cache slot", async () => {
    const { result } = renderStreamAndQuery("job-1", evaluationKeys.findings("job-1"));
    act(() => {
      MockEventSource.last.emit("finding", { id: 1, practice_id: "P1" });
      MockEventSource.last.emit("finding", { id: 2, practice_id: "P2" });
    });
    await waitFor(() => expect(result.current.data).toHaveLength(2));
    // Frames land in order and keep every wire field. They are no longer
    // written verbatim: see the normalisation test below.
    expect(result.current.data.map((f) => f.id)).toEqual([1, 2]);
    expect(result.current.data.map((f) => f.practice_id)).toEqual(["P1", "P2"]);
  });

  it("normalises a finding frame so components can read `principle`", async () => {
    // The frame is serialised straight off the payload, so it says
    // practice_id where every component reads principle. Writing it verbatim
    // left the live feed's rule column blank for the whole run.
    const { result } = renderStreamAndQuery("job-1", evaluationKeys.findings("job-1"));
    act(() => {
      MockEventSource.last.emit("finding", {
        id: 7, practice_id: "Authenticity", severity: "major",
        file: "a.py", line: 3, end_line: 5, carried_forward: true,
        confidence: 25, verdict: "fail",
      });
    });
    await waitFor(() => expect(result.current.data).toHaveLength(1));
    const finding = result.current.data[0];
    expect(finding.principle).toBe("Authenticity");
    expect(finding.endLine).toBe(5);
    expect(finding.carriedForward).toBe(true);
    // Wire-only fields the model does not carry must survive the merge.
    expect(finding.id).toBe(7);
    expect(finding.confidence).toBe(25);
    expect(finding.verdict).toBe("fail");
  });

  it("writes dimension-completed events as a map keyed by dimension", async () => {
    const { result } = renderStreamAndQuery("job-1", evaluationKeys.dimensions("job-1"));
    act(() => {
      MockEventSource.last.emit("dimension-completed", {
        dimension: "security", score: 90,
      });
    });
    await waitFor(() => {
      expect(result.current.data).toEqual({
        security: { dimension: "security", score: 90 },
      });
    });
  });

  it("shares one EventSource between every subscriber to the same run", () => {
    // Five History rows for one run used to hold five connections; browsers
    // cap SSE connections per origin at six.
    const wrapper = withQueryClient();
    const rows = 5;
    const { unmount } = renderHook(
      () => { for (let i = 0; i < rows; i += 1) useRunEventStream("job-shared"); },
      { wrapper },
    );
    expect(MockEventSource.instances).toHaveLength(1);
    // Released once the last subscriber goes, not before.
    unmount();
    expect(MockEventSource.instances[0].closed).toBe(true);
  });

  it("keeps the stream open while any subscriber remains", () => {
    const wrapper = withQueryClient();
    const first = renderHook(() => useRunEventStream("job-shared"), { wrapper });
    const source = MockEventSource.last;
    first.unmount();
    expect(source.closed).toBe(true);
    // Different QueryClients are different registries: a fresh wrapper opens its own.
    renderHook(() => useRunEventStream("job-shared"), { wrapper: withQueryClient() });
    expect(MockEventSource.instances).toHaveLength(2);
  });

  it("reports the connection state so the poll policy can fall back", () => {
    const wrapper = withQueryClient();
    const { result } = renderHook(() => useRunEventStream("job-err"), { wrapper });
    expect(result.current).toBe(STREAM_STATE.OPEN);
    act(() => MockEventSource.last.fail());
    expect(result.current).toBe(STREAM_STATE.ERROR);
    act(() => MockEventSource.last.open());
    expect(result.current).toBe(STREAM_STATE.OPEN);
    act(() => MockEventSource.last.emit("done", {}));
    expect(result.current).toBe(STREAM_STATE.IDLE);
  });

  it("reports IDLE when there is no job", () => {
    const { result } = renderHook(() => useRunEventStream(""), { wrapper: withQueryClient() });
    expect(result.current).toBe(STREAM_STATE.IDLE);
  });

  it("closes the source on done event", async () => {
    renderStreamAndQuery("job-1", evaluationKeys.status("job-1"));
    act(() => {
      MockEventSource.last.emit("done", { state: "done" });
    });
    expect(MockEventSource.last.closed).toBe(true);
  });

  it("does not open EventSource when jobId is empty", () => {
    renderStreamAndQuery("", evaluationKeys.status(""));
    expect(MockEventSource.last).toBeNull();
  });

  // Every terminal state invalidates the same way; a new one is a row here.
  it.each([
    ["done", "job-term-1"],
    ["failed", "job-term-2"],
    ["cancelled", "job-term-3"],
  ])("invalidates project trend on terminal status (%s)", (state, jobId) => {
    const { invalidateSpy } = renderStreamWithSpy(jobId);
    act(() => {
      MockEventSource.last.emit("status", { state });
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: projectKeys.all() });
  });

  it("does NOT invalidate project trend on non-terminal status", () => {
    const { invalidateSpy } = renderStreamWithSpy("job-running");
    act(() => {
      MockEventSource.last.emit("status", { state: "running" });
    });
    const sawProjectInvalidate = invalidateSpy.mock.calls.some(
      ([arg]) => Array.isArray(arg?.queryKey) && arg.queryKey[0] === "project",
    );
    expect(sawProjectInvalidate).toBe(false);
  });
});
