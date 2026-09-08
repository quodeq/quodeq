import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import React from "react";
import { useEvaluation } from "./useEvaluation";
import { withQueryClient } from "../../../test-utils/withQueryClient.jsx";
import { ApiProvider } from "../../../api/ApiContext.jsx";
import { PROVIDER_CONFIGURED_MARKER } from "../../../constants.js";

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
    // localStorage is shared across tests in this file; the api-key cases
    // below would otherwise leak a stored key into every later test.
    localStorage.removeItem("cc-ollama-api-key");
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

  it("startEvaluation never forwards the 'configured' sentinel as an api key", async () => {
    // A key saved through the current flow leaves only the sentinel here
    // (see useProviderSettings.js). Sending it would hand the provider a
    // bogus credential and skip the backend's own get_api_key_secure
    // lookup, which is what actually holds the real key.
    localStorage.setItem("cc-ollama-api-key", PROVIDER_CONFIGURED_MARKER);
    fakeApi.startEvaluation.mockResolvedValue({ jobId: "j4", status: "pending", dimensions: [] });
    const { result } = renderHook(() => useEvaluation(), { wrapper: makeWrapper() });
    await act(async () => {
      await result.current.startEvaluation({ repo: "x", dimensions: ["security"] });
    });
    const [payload] = fakeApi.startEvaluation.mock.calls.at(-1);
    expect(payload.apiKey).toBeUndefined();
  });

  it("startEvaluation still forwards a genuine legacy raw api key", async () => {
    // Installs that saved a key through the (since-deleted) Settings input
    // still have the raw value in this browser's localStorage and nothing
    // migrated it. Dropping it outright silently sent no key at all for
    // them — a live regression, not just dead code.
    localStorage.setItem("cc-ollama-api-key", "sk-legacy-raw-value");
    fakeApi.startEvaluation.mockResolvedValue({ jobId: "j5", status: "pending", dimensions: [] });
    const { result } = renderHook(() => useEvaluation(), { wrapper: makeWrapper() });
    await act(async () => {
      await result.current.startEvaluation({ repo: "x", dimensions: ["security"] });
    });
    const [payload] = fakeApi.startEvaluation.mock.calls.at(-1);
    expect(payload.apiKey).toBe("sk-legacy-raw-value");
  });

  it("startEvaluation sends no api key when nothing is stored", async () => {
    fakeApi.startEvaluation.mockResolvedValue({ jobId: "j6", status: "pending", dimensions: [] });
    const { result } = renderHook(() => useEvaluation(), { wrapper: makeWrapper() });
    await act(async () => {
      await result.current.startEvaluation({ repo: "x", dimensions: ["security"] });
    });
    const [payload] = fakeApi.startEvaluation.mock.calls.at(-1);
    expect(payload).not.toHaveProperty("apiKey");
  });
});
