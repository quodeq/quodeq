/**
 * Stream-driven behaviour of useEvaluation's status query: a healthy stream
 * means no fast poll, a broken one falls back to it.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { MockEventSource } from "../../../test-utils/MockEventSource.js";

const JOB = { jobId: "j-sse", status: "running", dimensions: [] };

const fakeApi = {
  getEvaluation: vi.fn(),
  startEvaluation: vi.fn(),
  cancelEvaluation: vi.fn(),
  listEvaluations: vi.fn(),
};

// Imported after vi.resetModules() so the providers are the same module
// instances the freshly imported hook reads its contexts from.
async function makeWrapper() {
  const { withQueryClient } = await import("../../../test-utils/withQueryClient.jsx");
  const { ApiProvider } = await import("../../../api/ApiContext.jsx");
  const QueryWrapper = withQueryClient();
  return function Wrapper({ children }) {
    return (
      <QueryWrapper>
        <ApiProvider value={fakeApi}>{children}</ApiProvider>
      </QueryWrapper>
    );
  };
}

async function renderWithSseOn() {
  vi.resetModules();
  const { useEvaluation } = await import("./useEvaluation.js");
  const { JOB_POLL_MS } = await import("./useEvaluation.helpers.js");
  const utils = renderHook(() => useEvaluation(), { wrapper: await makeWrapper() });
  await waitFor(() => expect(utils.result.current.job?.jobId).toBe("j-sse"));
  return { ...utils, JOB_POLL_MS };
}

describe("useEvaluation status polling under SSE", () => {
  beforeEach(() => {
    Object.values(fakeApi).forEach((fn) => fn.mockReset?.());
    fakeApi.getEvaluation.mockResolvedValue(JOB);
    // The resume path finds the running job and subscribes to its stream.
    fakeApi.listEvaluations.mockResolvedValue([JOB]);
    vi.stubGlobal("EventSource", MockEventSource);
    MockEventSource.last = null;
    MockEventSource.instances = [];
  });

  it("does not fast-poll while the stream is healthy", async () => {
    const { JOB_POLL_MS } = await renderWithSseOn();
    const calls = fakeApi.getEvaluation.mock.calls.length;
    await act(async () => {
      await new Promise((r) => setTimeout(r, JOB_POLL_MS + 200));
    });
    expect(fakeApi.getEvaluation.mock.calls.length).toBe(calls);
  });

  it("falls back to a REST poll within one tick once the stream errors", async () => {
    const { JOB_POLL_MS } = await renderWithSseOn();
    expect(MockEventSource.last).not.toBeNull();
    const calls = fakeApi.getEvaluation.mock.calls.length;
    act(() => MockEventSource.last.fail());
    await waitFor(
      () => expect(fakeApi.getEvaluation.mock.calls.length).toBeGreaterThan(calls),
      { timeout: JOB_POLL_MS + 500 },
    );
  });
});
