import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import React from "react";
import { useEvaluation } from "./useEvaluation";
import { withQueryClient } from "../../../test-utils/withQueryClient.jsx";
import { ApiProvider } from "../../../api/ApiContext.jsx";

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
});
