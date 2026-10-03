import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { useEvaluationQueries } from "./useEvaluationQueries.js";
import { evaluationKeys } from "../../../api/queryKeys.js";

// The findings slot is subscribe-only: useRunEventStream writes each admitted
// finding frame into it and this hook groups what is there. These tests
// stand in for the stream by writing to the same cache key.

const ROW = {
  principle: "Authenticity",
  req: "S-AUT-3",
  file: "src/quodeq/api/_assistant_helpers.py",
  line: 116,
  severity: "minor",
  dimension: "security",
};

function makeApi() {
  // Only the status request exists: a findings request would throw here.
  return {
    getEvaluation: vi.fn().mockResolvedValue({
      jobId: "job-1", status: "running", outputProject: "proj", outputRunId: "run-1",
      dimensions: ["security", "usability"],
    }),
  };
}

function renderQueries(api) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const wrapper = ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const rendered = renderHook(() => useEvaluationQueries(api, "job-1"), { wrapper });
  const stream = (...rows) => act(() => {
    client.setQueryData(evaluationKeys.findings("job-1"), (prev = []) => [...prev, ...rows]);
  });
  return { ...rendered, stream };
}

describe("useEvaluationQueries", () => {
  it("starts with no findings and never requests any", async () => {
    const api = makeApi();
    const { result } = renderQueries(api);
    await waitFor(() => expect(result.current.job).not.toBeNull());
    expect(result.current.liveViolations).toEqual({});
    expect(api.getEvaluation).toHaveBeenCalledWith("job-1");
  });

  it("groups the rows the stream wrote by dimension, in arrival order", async () => {
    const { result, stream } = renderQueries(makeApi());
    await stream(ROW, { ...ROW, line: 200 }, { ...ROW, dimension: "usability", file: "src/b.py" });
    await waitFor(() => expect(result.current.liveViolations.usability).toHaveLength(1));
    expect(result.current.liveViolations.security.map((r) => r.line)).toEqual([116, 200]);
    expect(result.current.liveViolations.security[0].principle).toBe("Authenticity");
  });

  it("files a row without a dimension under the placeholder group", async () => {
    const { result, stream } = renderQueries(makeApi());
    const { dimension: unused, ...bare } = ROW;
    await stream(bare);
    await waitFor(() => expect(result.current.liveViolations._).toHaveLength(1));
  });

  it("keeps one grouped object while the slot is unchanged", async () => {
    const { result, rerender, stream } = renderQueries(makeApi());
    await stream(ROW);
    await waitFor(() => expect(result.current.liveViolations.security).toHaveLength(1));
    const grouped = result.current.liveViolations;
    rerender();
    // A new object every render would re-render every live subscriber.
    expect(result.current.liveViolations).toBe(grouped);
  });
});
