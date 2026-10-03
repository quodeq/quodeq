import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEvaluation } from "./useEvaluation";
import { CANCEL_CHOICE } from "../cancelDialog.js";
import { CANCEL_RECONCILE_DELAYS_MS } from "./useEvaluationMutations.js";
import { ApiProvider } from "../../../api/ApiContext.jsx";
import { MockEventSource } from "../../../test-utils/MockEventSource.js";

vi.mock("../../../utils/confirmDialog.js", () => ({
  confirmDialog: vi.fn().mockResolvedValue({ ok: true, checked: false }),
}));
vi.mock("../../../utils/chooseDialog.js", () => ({
  chooseDialog: vi.fn().mockResolvedValue("preserve"),
}));

const fakeApi = {
  getEvaluation: vi.fn(),
  startEvaluation: vi.fn(),
  cancelEvaluation: vi.fn(),
  listEvaluations: vi.fn().mockResolvedValue([]),
};

// A keep-findings cancel returns before the run has drained and the server
// has scored its finished dims, so the views must refresh again later.
// Under SSE nothing else would refetch them.

async function startThenCancel({ discard }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  fakeApi.startEvaluation.mockResolvedValue({ jobId: "j-rec", status: "running", dimensions: [] });
  fakeApi.cancelEvaluation.mockResolvedValue({ ok: true });
  function Wrapper({ children }) {
    return (
      <QueryClientProvider client={client}>
        <ApiProvider value={fakeApi}>{children}</ApiProvider>
      </QueryClientProvider>
    );
  }
  const hook = renderHook(() => useEvaluation(), { wrapper: Wrapper });
  await act(async () => {
    await hook.result.current.startEvaluation({ repo: "x", dimensions: [] });
  });
  await waitFor(() => expect(hook.result.current.job?.jobId).toBe("j-rec"));
  const spy = vi.spyOn(client, "invalidateQueries");
  await act(async () => {
    await hook.result.current.cancelEvaluation({ confirm: async () => (discard ? CANCEL_CHOICE.DISCARD : CANCEL_CHOICE.PRESERVE) });
  });
  // onSuccess refreshes the project once right away; count only the delayed ones.
  await waitFor(() => expect(projectRefreshes(spy)).toBeGreaterThan(0));
  spy.mockClear();
  return { client, hook, spy };
}

function projectRefreshes(spy) {
  return spy.mock.calls.filter(([arg]) => arg?.queryKey?.[0] === "project").length;
}

describe("useEvaluation cancel reconcile", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    Object.values(fakeApi).forEach((fn) => fn.mockReset?.());
    fakeApi.listEvaluations.mockResolvedValue([]);
    // jsdom has no EventSource; the stream opens against the mock.
    vi.stubGlobal("EventSource", MockEventSource);
    localStorage.setItem("cc-active-provider", "ollama");
    localStorage.setItem("cc-ollama-model", "llama3.1");
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllEnvs();
  });

  it("refreshes the project and job again at each delay after a keep-findings cancel", async () => {
    const { spy } = await startThenCancel({ discard: false });
    let elapsed = 0;
    for (const [i, ms] of CANCEL_RECONCILE_DELAYS_MS.entries()) {
      await act(async () => { vi.advanceTimersByTime(ms - elapsed); });
      elapsed = ms;
      expect(projectRefreshes(spy)).toBe(i + 1);
    }
    expect(spy).toHaveBeenCalledWith({ queryKey: ["evaluation", "j-rec"] });
  });

  it("schedules nothing after a discard (the run is gone)", async () => {
    const { spy } = await startThenCancel({ discard: true });
    await act(async () => { vi.advanceTimersByTime(Math.max(...CANCEL_RECONCILE_DELAYS_MS)); });
    expect(projectRefreshes(spy)).toBe(0);
  });

  it("drops the pending refreshes on unmount", async () => {
    const { spy, hook } = await startThenCancel({ discard: false });
    hook.unmount();
    await act(async () => { vi.advanceTimersByTime(Math.max(...CANCEL_RECONCILE_DELAYS_MS)); });
    expect(projectRefreshes(spy)).toBe(0);
  });
});
