import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useEvaluation } from "./useEvaluation";
import { ADOPT_POLL_MS } from "./useEvaluation.helpers.js";
import { withQueryClient } from "../../../test-utils/withQueryClient.jsx";
import { ApiProvider } from "../../../api/ApiContext.jsx";
import { MockEventSource } from "../../../test-utils/MockEventSource.js";

// The app mounts useEvaluation once, at start. A run that begins later (the
// nightly, a PR review, a terminal run) is noticed by checking again every
// ADOPT_POLL_MS while nothing is held.

const fakeApi = {
  getEvaluation: vi.fn(),
  startEvaluation: vi.fn(),
  cancelEvaluation: vi.fn(),
  listEvaluations: vi.fn(),
};

function makeWrapper() {
  const QueryWrapper = withQueryClient();
  return function Wrapper({ children }) {
    return (
      <QueryWrapper>
        <ApiProvider value={fakeApi}>{children}</ApiProvider>
      </QueryWrapper>
    );
  };
}

const nightly = { jobId: "ext-nightly", status: "running", source: "external", dimensions: ["security"] };

// waitFor polls on setInterval, which these tests fake; settle on real
// setTimeout turns instead.
const SETTLE_TRIES = 50;
async function waitFor(check) {
  for (let i = 0; ; i += 1) {
    try {
      check();
      return;
    } catch (err) {
      if (i >= SETTLE_TRIES) throw err;
      await act(() => new Promise((r) => setTimeout(r, 10)));
    }
  }
}

async function tick() {
  await act(async () => { vi.advanceTimersByTime(ADOPT_POLL_MS); });
}

describe("useEvaluation idle adoption", () => {
  beforeEach(() => {
    Object.values(fakeApi).forEach((fn) => fn.mockReset());
    fakeApi.listEvaluations.mockResolvedValue([]);
    fakeApi.getEvaluation.mockImplementation(async (id) => ({ ...nightly, jobId: id }));
    vi.stubGlobal("EventSource", MockEventSource);
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("adopts a run that starts after the app opened", async () => {
    const { result } = renderHook(() => useEvaluation(), { wrapper: makeWrapper() });
    await waitFor(() => expect(fakeApi.listEvaluations).toHaveBeenCalledTimes(1));
    expect(result.current.job).toBeNull();
    fakeApi.listEvaluations.mockResolvedValue([nightly]);
    await tick();
    await waitFor(() => expect(result.current.job?.jobId).toBe("ext-nightly"));
  });

  it("stops checking while a run is held", async () => {
    fakeApi.listEvaluations.mockResolvedValue([nightly]);
    const { result } = renderHook(() => useEvaluation(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.job?.jobId).toBe("ext-nightly"));
    const calls = fakeApi.listEvaluations.mock.calls.length;
    await tick();
    await tick();
    expect(fakeApi.listEvaluations.mock.calls.length).toBe(calls);
  });

  it("a later failed check is only logged, not shown as an error", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { result } = renderHook(() => useEvaluation(), { wrapper: makeWrapper() });
    await waitFor(() => expect(fakeApi.listEvaluations).toHaveBeenCalledTimes(1));
    fakeApi.listEvaluations.mockRejectedValue(new Error("network"));
    await tick();
    await waitFor(() => expect(warn).toHaveBeenCalled());
    expect(result.current.jobError).toBeNull();
    warn.mockRestore();
  });

  it("after closing a finished run, the next check adopts another running one", async () => {
    fakeApi.listEvaluations.mockResolvedValue([{ ...nightly, status: "done" }]);
    fakeApi.getEvaluation.mockImplementation(async (id) => ({ ...nightly, jobId: id, status: "done" }));
    const { result } = renderHook(() => useEvaluation(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.job?.jobId).toBe("ext-nightly"));
    act(() => result.current.clearJob());
    const pr = { ...nightly, jobId: "ext-pr" };
    fakeApi.listEvaluations.mockResolvedValue([pr]);
    fakeApi.getEvaluation.mockImplementation(async (id) => ({ ...pr, jobId: id }));
    await tick();
    await waitFor(() => expect(result.current.job?.jobId).toBe("ext-pr"));
  });

  it("a finished run left on screen gives way to a new running one", async () => {
    const done = { ...nightly, jobId: "ext-done", status: "done" };
    fakeApi.listEvaluations.mockResolvedValue([done]);
    fakeApi.getEvaluation.mockImplementation(async (id) => (id === "ext-done" ? done : { ...nightly, jobId: id }));
    const { result } = renderHook(() => useEvaluation(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.job?.jobId).toBe("ext-done"));
    fakeApi.listEvaluations.mockResolvedValue([{ ...nightly, jobId: "ext-pr" }]);
    await tick();
    await waitFor(() => expect(result.current.job?.jobId).toBe("ext-pr"));
  });
});
