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


// Split from useEvaluation.test.jsx: cancelEvaluation's query
// invalidation, started-project tracking, discard vs keep-findings.

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
});
