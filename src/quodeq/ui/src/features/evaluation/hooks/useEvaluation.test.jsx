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
    import.meta.env.VITE_USE_SSE_EVENTS = "false";
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

  it("cancelEvaluation surfaces an error and clears the job when the API rejects", async () => {
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
      expect(result.current.job).toBeNull();
    });
  });

  it("startEvaluation surfaces a useful error when no provider is configured", async () => {
    localStorage.removeItem("cc-active-provider");
    const { result } = renderHook(() => useEvaluation(), { wrapper: makeWrapper() });
    await expect(
      result.current.startEvaluation({ repo: "x", dimensions: [] }),
    ).rejects.toThrow(/provider/i);
    await waitFor(() => expect(result.current.jobError).toMatch(/provider/i));
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
