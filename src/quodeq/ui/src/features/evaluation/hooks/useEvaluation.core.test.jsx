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


// Split from useEvaluation.test.jsx: public shape, startEvaluation
// cache-seeding/invalidation, clearJob, liveViolations, and Settings merge.

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
});
