import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";

// The lifecycle hook composes useEvaluation; mock it so tests can control
// the job state without a QueryClient or API layer.
const evaluationState = {
  job: null,
  jobError: null,
  liveViolations: {},
  startEvaluation: vi.fn(),
  clearJob: vi.fn(),
  cancelEvaluation: vi.fn(),
  startedProject: null,
};
vi.mock("../features/evaluation/hooks/useEvaluation.js", () => ({
  useEvaluation: () => evaluationState,
  LOCAL_API_PROVIDERS: new Set(["ollama", "llamacpp", "omlx"]),
}));

import { useEvaluationLifecycle } from "./useEvaluationLifecycle.js";

function renderLifecycle() {
  return renderHook(() =>
    useEvaluationLifecycle({
      settings: {},
      navigation: { navTab: vi.fn(), navReset: vi.fn() },
      projects: {
        loadProjects: vi.fn().mockResolvedValue([]),
        setProjects: vi.fn(),
        selectProjectAndRun: vi.fn(),
      },
    }),
  );
}

describe("useEvaluationLifecycle blocked start", () => {
  beforeEach(() => {
    evaluationState.job = null;
    evaluationState.jobError = null;
    evaluationState.startEvaluation = vi.fn();
    localStorage.setItem("cc-active-provider", "ollama");
    localStorage.setItem("cc-ollama-model", "llama3.1");
  });

  it("surfaces a visible error instead of silently ignoring a start while a job runs", () => {
    // Regression (v1.6.0): pressing scan while another evaluation ran was
    // swallowed with only a console.warn. The user believed the visible
    // (older) evaluation was the one they just launched.
    evaluationState.job = { jobId: "j-running", status: "running" };
    const { result } = renderLifecycle();

    act(() => {
      result.current.handleStartEvaluation({ repo: "x", dimensions: [] });
    });

    expect(evaluationState.startEvaluation).not.toHaveBeenCalled();
    expect(result.current.jobError).toMatch(/already running/i);
  });

  it("clears the blocked-start error once a start goes through", () => {
    evaluationState.job = { jobId: "j-running", status: "running" };
    const { result, rerender } = renderLifecycle();
    act(() => {
      result.current.handleStartEvaluation({ repo: "x", dimensions: [] });
    });
    expect(result.current.jobError).toMatch(/already running/i);

    evaluationState.job = null;
    rerender();
    act(() => {
      result.current.handleStartEvaluation({ repo: "y", dimensions: [] });
    });
    expect(evaluationState.startEvaluation).toHaveBeenCalled();
    expect(result.current.jobError).toBeNull();
  });

  it("returns false from a blocked start so callers can keep one-shot UI state", () => {
    // ReEvaluateCard consumes the clean-scan "once" toggle when a start
    // succeeds; a blocked start must not eat it.
    evaluationState.job = { jobId: "j-running", status: "running" };
    const { result } = renderLifecycle();
    let returned;
    act(() => {
      returned = result.current.handleStartEvaluation({ repo: "x", dimensions: [] });
    });
    expect(returned).toBe(false);
  });
});
