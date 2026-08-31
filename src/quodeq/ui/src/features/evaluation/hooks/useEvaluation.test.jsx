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

describe("useEvaluation", () => {
  beforeEach(() => {
    Object.values(fakeApi).forEach((fn) => fn.mockReset?.());
    fakeApi.listEvaluations.mockResolvedValue([]);
    // Default: SSE off — refetchInterval path
    vi.stubEnv("VITE_USE_SSE_EVENTS", "false");
    // preparePayload reads localStorage; seed a working provider+model.
    localStorage.setItem("cc-active-provider", "ollama");
    localStorage.setItem("cc-ollama-model", "llama3.1");
  });

  it("returns the documented public shape", () => {
    const { result } = renderHook(() => useEvaluation(), {
      wrapper: makeWrapper(),
    });
    expect(result.current).toHaveProperty("job");
    expect(result.current).toHaveProperty("jobError");
    expect(result.current).toHaveProperty("liveViolations");
    expect(result.current).toHaveProperty("startEvaluation");
    expect(result.current).toHaveProperty("clearJob");
    expect(result.current).toHaveProperty("cancelEvaluation");
  });

  it("startEvaluation seeds the cache with the created job", async () => {
    fakeApi.startEvaluation.mockResolvedValue({
      jobId: "j1",
      status: "pending",
      dimensions: [],
    });
    const { result } = renderHook(() => useEvaluation(), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      await result.current.startEvaluation({ repo: "x", dimensions: [] });
    });
    await waitFor(() => {
      expect(result.current.job?.jobId).toBe("j1");
    });
  });

  it("startEvaluation invalidates project queries so History sees the new run immediately", async () => {
    // Regression: pre-fix, History stayed stale until either polling
    // ticked (only fires when in_progress runs are already visible) or
    // the user navigated away and back. Result: 'running' row took
    // ~10-30s to appear after Start. The fix invalidates the project
    // subtree on success so subscribed queries refetch right away.
    const { QueryClient, QueryClientProvider } = await import("@tanstack/react-query");
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    fakeApi.startEvaluation.mockResolvedValue({
      jobId: "jx", status: "pending", dimensions: [],
    });
    function Wrapper({ children }) {
      return (
        <QueryClientProvider client={client}>
          <ApiProvider value={fakeApi}>{children}</ApiProvider>
        </QueryClientProvider>
      );
    }
    const { result } = renderHook(() => useEvaluation(), { wrapper: Wrapper });
    await act(async () => {
      await result.current.startEvaluation({ repo: "x", dimensions: [] });
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["project"] });
  });

  it("clearJob resets job state", async () => {
    fakeApi.startEvaluation.mockResolvedValue({
      jobId: "j2",
      status: "pending",
      dimensions: [],
    });
    const { result } = renderHook(() => useEvaluation(), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      await result.current.startEvaluation({ repo: "x", dimensions: [] });
    });
    act(() => result.current.clearJob());
    await waitFor(() => expect(result.current.job).toBeNull());
  });

  it("liveViolations is an empty object when no findings", () => {
    const { result } = renderHook(() => useEvaluation(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.liveViolations).toEqual({});
  });

  it("startEvaluation merges Settings (provider/model/subagents) from localStorage", async () => {
    fakeApi.startEvaluation.mockResolvedValue({ jobId: "j3", status: "pending", dimensions: [] });
    const { result } = renderHook(() => useEvaluation(), { wrapper: makeWrapper() });
    await act(async () => {
      await result.current.startEvaluation({ repo: "x", dimensions: ["security"] });
    });
    expect(fakeApi.startEvaluation).toHaveBeenCalledWith(
      expect.objectContaining({
        repo: "x",
        aiCmd: "ollama",
        aiModel: "llama3.1",
      }),
    );
  });

  it("cancelEvaluation invalidates project queries so History drops the cancelled run immediately", async () => {
    // Regression: pre-fix, after cancel the History row stayed on the
    // 'performing an evaluation...' placeholder until either polling
    // ticked or (under SSE) the terminal-status event arrived. Mirrors
    // startMutation's existing project-subtree invalidate.
    const { QueryClient, QueryClientProvider } = await import("@tanstack/react-query");
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    fakeApi.startEvaluation.mockResolvedValue({
      jobId: "j-cancel-1", status: "running", dimensions: [],
    });
    fakeApi.cancelEvaluation.mockResolvedValue({ ok: true });
    function Wrapper({ children }) {
      return (
        <QueryClientProvider client={client}>
          <ApiProvider value={fakeApi}>{children}</ApiProvider>
        </QueryClientProvider>
      );
    }
    const { result } = renderHook(() => useEvaluation(), { wrapper: Wrapper });
    await act(async () => {
      await result.current.startEvaluation({ repo: "x", dimensions: [] });
    });
    await waitFor(() => expect(result.current.job?.jobId).toBe("j-cancel-1"));
    // Spy AFTER start so we only observe cancel's invalidations.
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    await act(async () => {
      await result.current.cancelEvaluation();
    });
    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["project"] });
    });
  });

  it("tracks the project an evaluation was started for and strips it from the API payload", async () => {
    // The in-progress card needs the launching project's identity before
    // the backend's report-path marker resolves outputProject. uiProject
    // is UI-side bookkeeping only and must not leak into the HTTP body.
    fakeApi.startEvaluation.mockResolvedValue({
      jobId: "j-started", status: "pending", dimensions: [],
    });
    const { result } = renderHook(() => useEvaluation(), { wrapper: makeWrapper() });
    await act(async () => {
      await result.current.startEvaluation({
        repo: "x", dimensions: [], uiProject: "uuid-b",
      });
    });
    expect(result.current.startedProject).toBe("uuid-b");
    expect(fakeApi.startEvaluation).toHaveBeenCalledWith(
      expect.not.objectContaining({ uiProject: expect.anything() }),
    );
    act(() => result.current.clearJob());
    expect(result.current.startedProject).toBeNull();
  });

  it("cancelEvaluation with discard clears the job immediately", async () => {
    // With discard the server deletes the run entirely (dir + index row +
    // job entry). Any further status polling would 404, so the hook must
    // drop the job on success instead of waiting for a terminal status
    // that will never arrive.
    const { chooseDialog } = await import("../../../utils/chooseDialog.js");
    chooseDialog.mockResolvedValueOnce("discard");
    fakeApi.startEvaluation.mockResolvedValue({
      jobId: "j-disc", status: "running", dimensions: [],
    });
    fakeApi.cancelEvaluation.mockResolvedValue({ ok: true, discarded: true });
    const { result } = renderHook(() => useEvaluation(), { wrapper: makeWrapper() });
    await act(async () => {
      await result.current.startEvaluation({ repo: "x", dimensions: [] });
    });
    await waitFor(() => expect(result.current.job?.jobId).toBe("j-disc"));

    await act(async () => {
      await result.current.cancelEvaluation();
    });

    expect(fakeApi.cancelEvaluation).toHaveBeenCalledWith("j-disc", { discard: true });
    await waitFor(() => expect(result.current.job).toBeNull());
    expect(result.current.jobError).toBeNull();
  });

  it("cancelEvaluation with keep-findings retains the job for the terminal card", async () => {
    // Guard: the preserve path must NOT clear the job — the panel flips to
    // the cancelled card via polling/SSE and the user dismisses it.
    fakeApi.startEvaluation.mockResolvedValue({
      jobId: "j-keep", status: "running", dimensions: [],
    });
    fakeApi.cancelEvaluation.mockResolvedValue({ ok: true, discarded: false });
    const { result } = renderHook(() => useEvaluation(), { wrapper: makeWrapper() });
    await act(async () => {
      await result.current.startEvaluation({ repo: "x", dimensions: [] });
    });
    await waitFor(() => expect(result.current.job?.jobId).toBe("j-keep"));

    await act(async () => {
      await result.current.cancelEvaluation();
    });

    expect(fakeApi.cancelEvaluation).toHaveBeenCalledWith("j-keep", { discard: false });
    expect(result.current.job).not.toBeNull();
  });

  it("cancelEvaluation surfaces an error and keeps the job on a status-less rejection", async () => {
    // A rejection without an HTTP status (network drop, request timeout)
    // is transient: the scan may still be running server-side, so the job
    // must stay visible. Only 409/404 clear it (see the cancel failure
    // handling suite below).
    fakeApi.startEvaluation.mockResolvedValue({
      jobId: "j-stuck",
      status: "running",
      dimensions: [],
    });
    fakeApi.cancelEvaluation.mockRejectedValue(new Error("Could not cancel job"));
    const { result } = renderHook(() => useEvaluation(), { wrapper: makeWrapper() });
    await act(async () => {
      await result.current.startEvaluation({ repo: "x", dimensions: [] });
    });
    await waitFor(() => expect(result.current.job?.jobId).toBe("j-stuck"));

    await act(async () => {
      await result.current.cancelEvaluation();
    });

    await waitFor(() => {
      expect(result.current.jobError).toMatch(/cancel/i);
    });
    expect(result.current.job?.jobId).toBe("j-stuck");
  });

  it("startEvaluation surfaces a useful error when no provider is configured", async () => {
    localStorage.removeItem("cc-active-provider");
    const { result } = renderHook(() => useEvaluation(), { wrapper: makeWrapper() });
    await expect(
      result.current.startEvaluation({ repo: "x", dimensions: [] }),
    ).rejects.toThrow(/provider/i);
    await waitFor(() => expect(result.current.jobError).toMatch(/provider/i));
  });

  it("startEvaluation surfaces the backend's specific message on a 400", async () => {
    // Regression: a server-side 400 (e.g. an invalid aiCmdPath override)
    // used to collapse into the generic "Failed to start evaluation.",
    // hiding the actionable reason the backend already wrote.
    const err = new Error(
      "Invalid AI command override: 'claude-v' was not found or is not executable",
    );
    err.status = 400;
    err.code = "INVALID_INPUT";
    fakeApi.startEvaluation.mockRejectedValue(err);
    const { result } = renderHook(() => useEvaluation(), { wrapper: makeWrapper() });
    await expect(
      result.current.startEvaluation({ repo: "x", dimensions: [] }),
    ).rejects.toThrow();
    await waitFor(() => expect(result.current.jobError).toMatch(/claude-v/));
  });

  it("startEvaluation shows translated copy for a mapped error code", async () => {
    const err = new Error("Too many evaluation requests");
    err.status = 429;
    err.code = "RATE_LIMITED";
    fakeApi.startEvaluation.mockRejectedValue(err);
    const { result } = renderHook(() => useEvaluation(), { wrapper: makeWrapper() });
    await expect(
      result.current.startEvaluation({ repo: "x", dimensions: [] }),
    ).rejects.toThrow();
    await waitFor(() =>
      expect(result.current.jobError).toBe("Too many requests. Wait a moment and try again."),
    );
  });

  it("startEvaluation falls back to the generic message when the failure carries no text", async () => {
    fakeApi.startEvaluation.mockRejectedValue(new Error(""));
    const { result } = renderHook(() => useEvaluation(), { wrapper: makeWrapper() });
    await expect(
      result.current.startEvaluation({ repo: "x", dimensions: [] }),
    ).rejects.toThrow();
    await waitFor(() =>
      expect(result.current.jobError).toBe("Failed to start evaluation."),
    );
  });

  it("adopts a running CLI-started external run on mount", async () => {
    const running = {
      jobId: "ext-abc",
      status: "running",
      source: "external",
      dimensions: ["security"],
    };
    fakeApi.listEvaluations.mockResolvedValue([running]);
    fakeApi.getEvaluation.mockResolvedValue(running);
    const { result } = renderHook(() => useEvaluation(), { wrapper: makeWrapper() });
    await waitFor(() => {
      expect(result.current.job?.jobId).toBe("ext-abc");
    });
    expect(fakeApi.listEvaluations).toHaveBeenCalledWith(
      expect.objectContaining({ states: ["running"] }),
    );
  });

  it("does not overwrite a user-started job when the resume resolves later", async () => {
    let resolveList;
    fakeApi.listEvaluations.mockReturnValue(
      new Promise((r) => {
        resolveList = r;
      }),
    );
    fakeApi.startEvaluation.mockResolvedValue({
      jobId: "j-fresh",
      status: "pending",
      dimensions: [],
    });
    const { result } = renderHook(() => useEvaluation(), { wrapper: makeWrapper() });
    await act(async () => {
      await result.current.startEvaluation({ repo: "x", dimensions: [] });
    });
    expect(result.current.job?.jobId).toBe("j-fresh");
    await act(async () => {
      resolveList([{ jobId: "ext-old", status: "running", source: "external" }]);
    });
    expect(result.current.job?.jobId).toBe("j-fresh");
  });

  it("ignores listEvaluations failure on mount", async () => {
    fakeApi.listEvaluations.mockRejectedValue(new Error("network"));
    const { result } = renderHook(() => useEvaluation(), { wrapper: makeWrapper() });
    await waitFor(() => expect(fakeApi.listEvaluations).toHaveBeenCalled());
    expect(result.current.job).toBeNull();
    expect(result.current.jobError).toBeNull();
  });
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
