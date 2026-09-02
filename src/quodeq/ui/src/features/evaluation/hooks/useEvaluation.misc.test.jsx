import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import React from "react";
import { useEvaluation } from "./useEvaluation";
import { withQueryClient } from "../../../test-utils/withQueryClient.jsx";
import { ApiProvider } from "../../../api/ApiContext.jsx";

vi.mock("../../../utils/confirmDialog.js", () => ({
  confirmDialog: vi.fn().mockResolvedValue({ ok: true, checked: false }),
}));

// chooseDialog renders a real DOM dialog and waits for a click; in jsdom
// that never resolves and the mutation never fires. Auto-resolve to a
// non-destructive choice so cancel-flow tests can drive cancelMutation.
vi.mock("../../../utils/chooseDialog.js", () => ({
  chooseDialog: vi.fn().mockResolvedValue("preserve"),
}));

const fakeApi = {
  getEvaluation: vi.fn(),
  startEvaluation: vi.fn(),
  cancelEvaluation: vi.fn(),
  getDimensionEval: vi.fn(),
  listEvaluations: vi.fn().mockResolvedValue([]),
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


// Split from useEvaluation.test.jsx: findingsRefetchInterval,
// cancel-failure-status handling, and preparePayload's honoring of
// caller-provided values.
//
// In the original single file, these describes are siblings of
// describe("useEvaluation", ...), whose beforeEach seeds
// cc-active-provider/cc-ollama-model in localStorage; jsdom's localStorage
// persists across describes within one file, so "cancel failure handling"
// and "preparePayload" implicitly relied on that seeding having already run.
// Split into a separate file, that implicit ordering is gone, so the same
// seeding is replicated explicitly here to preserve identical behavior.
beforeEach(() => {
  Object.values(fakeApi).forEach((fn) => fn.mockReset?.());
  fakeApi.listEvaluations.mockResolvedValue([]);
  vi.stubEnv("VITE_USE_SSE_EVENTS", "false");
  localStorage.setItem("cc-active-provider", "ollama");
  localStorage.setItem("cc-ollama-model", "llama3.1");
});

describe("findingsRefetchInterval", () => {
  it("polls while the job runs, stops when it reaches any terminal status", async () => {
    const { findingsRefetchInterval } = await import("./useEvaluation.js");
    expect(findingsRefetchInterval({ status: "running" }, false)).toBe(2000);
    expect(findingsRefetchInterval(null, false)).toBe(2000);
    for (const status of ["done", "failed", "cancelled", "lost", "completed"]) {
      expect(findingsRefetchInterval({ status }, false)).toBe(false);
    }
  });

  it("never polls under SSE", async () => {
    const { findingsRefetchInterval } = await import("./useEvaluation.js");
    expect(findingsRefetchInterval({ status: "running" }, true)).toBe(false);
  });
});

describe("cancel failure handling", () => {
  async function startJob(result) {
    fakeApi.startEvaluation.mockResolvedValue({ jobId: "j-c", status: "running", dimensions: [] });
    await act(async () => {
      await result.current.startEvaluation({ repo: "x", dimensions: [] });
    });
    await waitFor(() => expect(result.current.job?.jobId).toBe("j-c"));
  }

  it("keeps the job when cancel fails transiently (500/timeout)", async () => {
    // Clearing the job on ANY rejection let a slow SIGTERM-ignoring run be
    // dropped client-side (30s request timeout vs ~33s server cancel path),
    // unblocking a second concurrent scan on the same project.
    const err = new Error("boom");
    err.status = 500;
    fakeApi.cancelEvaluation.mockRejectedValue(err);
    const { result } = renderHook(() => useEvaluation(), { wrapper: makeWrapper() });
    await startJob(result);
    await act(async () => {
      await result.current.cancelEvaluation();
    });
    await waitFor(() => expect(result.current.jobError).toBeTruthy());
    expect(result.current.job?.jobId).toBe("j-c");
  });

  it("drops the job when the backend says it is no longer cancellable (409)", async () => {
    const err = new Error("not cancellable");
    err.status = 409;
    fakeApi.cancelEvaluation.mockRejectedValue(err);
    const { result } = renderHook(() => useEvaluation(), { wrapper: makeWrapper() });
    await startJob(result);
    await act(async () => {
      await result.current.cancelEvaluation();
    });
    await waitFor(() => expect(result.current.job).toBeNull());
  });
});

describe("preparePayload honors caller-provided values", () => {
  it("keeps an explicit timeLimit (including 0) instead of overwriting from Settings", async () => {
    // The wizard shows a TIME LIMIT field; its value used to be dead code
    // because the payload merge unconditionally re-read localStorage.
    localStorage.setItem("cc-ollama-time-limit", "600");
    fakeApi.startEvaluation.mockResolvedValue({ jobId: "j-w", status: "pending", dimensions: [] });
    const { result } = renderHook(() => useEvaluation(), { wrapper: makeWrapper() });
    await act(async () => {
      await result.current.startEvaluation({ repo: "x", dimensions: [], timeLimit: 0 });
    });
    expect(fakeApi.startEvaluation).toHaveBeenCalledWith(
      expect.objectContaining({ timeLimit: 0 }),
    );
  });

  it("uses the caller's provider and reads that provider's settings", async () => {
    // Wizard-launched runs name their provider; per-provider settings must
    // come from that provider's keys, not the active tab's.
    localStorage.setItem("cc-claude-model", "sonnet");
    localStorage.setItem("cc-claude-time-limit", "1200");
    fakeApi.startEvaluation.mockResolvedValue({ jobId: "j-w2", status: "pending", dimensions: [] });
    const { result } = renderHook(() => useEvaluation(), { wrapper: makeWrapper() });
    await act(async () => {
      await result.current.startEvaluation({ repo: "x", dimensions: [], aiCmd: "claude" });
    });
    expect(fakeApi.startEvaluation).toHaveBeenCalledWith(
      expect.objectContaining({ aiCmd: "claude", aiModel: "sonnet", timeLimit: 1200 }),
    );
  });

  it("includes the provider's command override when set", async () => {
    localStorage.setItem("cc-claude-model", "sonnet");
    localStorage.setItem("cc-claude-cmd-path", "/opt/bin/claude-api");
    fakeApi.startEvaluation.mockResolvedValue({ jobId: "j-w3", status: "pending", dimensions: [] });
    const { result } = renderHook(() => useEvaluation(), { wrapper: makeWrapper() });
    await act(async () => {
      await result.current.startEvaluation({ repo: "x", dimensions: [], aiCmd: "claude" });
    });
    expect(fakeApi.startEvaluation).toHaveBeenCalledWith(
      expect.objectContaining({ aiCmdPath: "/opt/bin/claude-api" }),
    );
  });

  it("omits the command when it still equals the provider default", async () => {
    localStorage.setItem("cc-claude-model", "sonnet");
    localStorage.setItem("cc-claude-cmd-path", "claude");
    fakeApi.startEvaluation.mockResolvedValue({ jobId: "j-w4", status: "pending", dimensions: [] });
    const { result } = renderHook(() => useEvaluation(), { wrapper: makeWrapper() });
    await act(async () => {
      await result.current.startEvaluation({ repo: "x", dimensions: [], aiCmd: "claude" });
    });
    const payload = fakeApi.startEvaluation.mock.calls.at(-1)[0];
    expect(payload).not.toHaveProperty("aiCmdPath");
  });
});
