import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useQuery, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useRunEventStream } from "./useRunEventStream";
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
  return { ...utils, invalidateSpy };
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
  });

  it("opens an EventSource against the events endpoint when SSE is enabled", () => {
    vi.stubEnv("VITE_USE_SSE_EVENTS", "true");
    renderStreamAndQuery("job-123", evaluationKeys.status("job-123"));
    expect(MockEventSource.last.url).toBe("/api/evaluations/job-123/events");
  });

  it("writes status events into evaluationKeys.status cache slot", async () => {
    vi.stubEnv("VITE_USE_SSE_EVENTS", "true");
    const { result } = renderStreamAndQuery("job-1", evaluationKeys.status("job-1"));
    act(() => {
      MockEventSource.last.emit("status", { state: "running", phase: "analyzing" });
    });
    await waitFor(() => {
      expect(result.current.data).toEqual({ state: "running", phase: "analyzing" });
    });
  });

  it("appends finding events into evaluationKeys.findings cache slot", async () => {
    vi.stubEnv("VITE_USE_SSE_EVENTS", "true");
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
    vi.stubEnv("VITE_USE_SSE_EVENTS", "true");
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
    vi.stubEnv("VITE_USE_SSE_EVENTS", "true");
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

  it("closes the source on done event", async () => {
    vi.stubEnv("VITE_USE_SSE_EVENTS", "true");
    renderStreamAndQuery("job-1", evaluationKeys.status("job-1"));
    act(() => {
      MockEventSource.last.emit("done", { state: "done" });
    });
    expect(MockEventSource.last.closed).toBe(true);
  });

  it("does not open EventSource when jobId is empty", () => {
    vi.stubEnv("VITE_USE_SSE_EVENTS", "true");
    renderStreamAndQuery("", evaluationKeys.status(""));
    expect(MockEventSource.last).toBeNull();
  });

  it("is a no-op when VITE_USE_SSE_EVENTS is not 'true'", () => {
    vi.stubEnv("VITE_USE_SSE_EVENTS", "false");
    renderStreamAndQuery("job-1", evaluationKeys.status("job-1"));
    expect(MockEventSource.last).toBeNull();
  });

  it("invalidates project trend on terminal status (done)", () => {
    vi.stubEnv("VITE_USE_SSE_EVENTS", "true");
    const { invalidateSpy } = renderStreamWithSpy("job-term-1");
    act(() => {
      MockEventSource.last.emit("status", { state: "done" });
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: projectKeys.all() });
  });

  it("invalidates project trend on terminal status (failed)", () => {
    vi.stubEnv("VITE_USE_SSE_EVENTS", "true");
    const { invalidateSpy } = renderStreamWithSpy("job-term-2");
    act(() => {
      MockEventSource.last.emit("status", { state: "failed" });
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: projectKeys.all() });
  });

  it("invalidates project trend on terminal status (cancelled)", () => {
    vi.stubEnv("VITE_USE_SSE_EVENTS", "true");
    const { invalidateSpy } = renderStreamWithSpy("job-term-3");
    act(() => {
      MockEventSource.last.emit("status", { state: "cancelled" });
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: projectKeys.all() });
  });

  it("does NOT invalidate project trend on non-terminal status", () => {
    vi.stubEnv("VITE_USE_SSE_EVENTS", "true");
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
