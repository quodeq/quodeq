import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEvaluationQueries } from "./useEvaluationQueries.js";
import { evaluationKeys } from "../../../api/queryKeys.js";

// A PR review's folder is deleted by the CI runner when the job ends. The
// status GET then answers 404: the screen keeps the last state it had, the
// job reads as ended, and the polling stops.
const api = { getEvaluation: vi.fn() };
const notFound = () => Object.assign(new Error("Job not found"), { status: 404 });
const last = { jobId: "ext-pr", status: "running", source: "external", commitSha: "7e506ae", dimensions: ["security"] };

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(evaluationKeys.status("ext-pr"), last);
  const wrapper = ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const hook = renderHook(() => useEvaluationQueries(api, "ext-pr", "error"), { wrapper });
  return { client, ...hook };
}

describe("a run whose folder vanished", () => {
  beforeEach(() => { api.getEvaluation.mockReset(); });

  it("keeps its last state and reads as ended", async () => {
    api.getEvaluation.mockImplementation(async () => { throw notFound(); });
    const { client, result } = setup();
    await act(() => client.invalidateQueries({ queryKey: evaluationKeys.status("ext-pr") }).catch(() => {}));
    await act(() => new Promise((r) => setTimeout(r, 50)));
    expect(result.current.job.vanished).toBe(true);
    // Finished for every consumer (no progress polling, no "tracking lost"
    // banner); the header says "ended" from `vanished`.
    expect(result.current.job.status).toBe("done");
    expect(result.current.job.commitSha).toBe("7e506ae");
  });

  it("a server error is not a vanished run", async () => {
    api.getEvaluation.mockImplementation(async () => { throw Object.assign(new Error("boom"), { status: 500 }); });
    const { client, result } = setup();
    // A server error is retried with backoff; only the first answer matters.
    act(() => { client.invalidateQueries({ queryKey: evaluationKeys.status("ext-pr") }).catch(() => {}); });
    await waitFor(() => expect(api.getEvaluation).toHaveBeenCalled());
    expect(result.current.job.vanished).toBeUndefined();
    expect(result.current.job.status).toBe("running");
  });

  it("stops asking once the run is gone", async () => {
    api.getEvaluation.mockImplementation(async () => { throw notFound(); });
    const { client, result } = setup();
    await act(() => client.invalidateQueries({ queryKey: evaluationKeys.status("ext-pr") }).catch(() => {}));
    await waitFor(() => expect(result.current.job.vanished).toBe(true));
    const query = client.getQueryCache().find({ queryKey: evaluationKeys.status("ext-pr") });
    const interval = query.observers[0].options.refetchInterval;
    expect(typeof interval === "function" ? interval(query) : interval).toBe(false);
  });
});
