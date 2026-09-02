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


// Split from useEvaluation.test.jsx: cancel-error surfacing,
// startEvaluation error-copy mapping, and external-run adoption on mount.

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
