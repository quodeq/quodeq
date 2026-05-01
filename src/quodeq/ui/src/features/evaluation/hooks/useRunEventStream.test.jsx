import { describe, it, expect, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useQuery } from "@tanstack/react-query";
import { useRunEventStream } from "./useRunEventStream";
import { evaluationKeys } from "../../../api/queryKeys.js";
import { withQueryClient } from "../../../test-utils/withQueryClient.jsx";

class MockEventSource {
  constructor(url) {
    this.url = url;
    this.listeners = {};
    MockEventSource.last = this;
  }
  addEventListener(event, handler) {
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(handler);
  }
  close() { this.closed = true; }
  emit(event, data) {
    (this.listeners[event] || []).forEach((h) =>
      h({ data: JSON.stringify(data), lastEventId: data?.id }),
    );
  }
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
    global.EventSource = MockEventSource;
    MockEventSource.last = null;
  });

  it("opens an EventSource against the events endpoint when SSE is enabled", () => {
    import.meta.env.VITE_USE_SSE_EVENTS = "true";
    renderStreamAndQuery("job-123", evaluationKeys.status("job-123"));
    expect(MockEventSource.last.url).toBe("/api/evaluations/job-123/events");
  });

  it("writes status events into evaluationKeys.status cache slot", async () => {
    import.meta.env.VITE_USE_SSE_EVENTS = "true";
    const { result } = renderStreamAndQuery("job-1", evaluationKeys.status("job-1"));
    act(() => {
      MockEventSource.last.emit("status", { state: "running", phase: "analyzing" });
    });
    await waitFor(() => {
      expect(result.current.data).toEqual({ state: "running", phase: "analyzing" });
    });
  });

  it("appends finding events into evaluationKeys.findings cache slot", async () => {
    import.meta.env.VITE_USE_SSE_EVENTS = "true";
    const { result } = renderStreamAndQuery("job-1", evaluationKeys.findings("job-1"));
    act(() => {
      MockEventSource.last.emit("finding", { id: 1, practice_id: "P1" });
      MockEventSource.last.emit("finding", { id: 2, practice_id: "P2" });
    });
    await waitFor(() => {
      expect(result.current.data).toEqual([
        { id: 1, practice_id: "P1" },
        { id: 2, practice_id: "P2" },
      ]);
    });
  });

  it("writes dimension-completed events as a map keyed by dimension", async () => {
    import.meta.env.VITE_USE_SSE_EVENTS = "true";
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
    import.meta.env.VITE_USE_SSE_EVENTS = "true";
    renderStreamAndQuery("job-1", evaluationKeys.status("job-1"));
    act(() => {
      MockEventSource.last.emit("done", { state: "done" });
    });
    expect(MockEventSource.last.closed).toBe(true);
  });

  it("does not open EventSource when jobId is empty", () => {
    import.meta.env.VITE_USE_SSE_EVENTS = "true";
    renderStreamAndQuery("", evaluationKeys.status(""));
    expect(MockEventSource.last).toBeNull();
  });

  it("is a no-op when VITE_USE_SSE_EVENTS is not 'true'", () => {
    import.meta.env.VITE_USE_SSE_EVENTS = "false";
    renderStreamAndQuery("job-1", evaluationKeys.status("job-1"));
    expect(MockEventSource.last).toBeNull();
  });
});
