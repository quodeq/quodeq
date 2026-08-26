import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { projectKeys } from "../api/queryKeys.js";

// The lifecycle hook composes useEvaluation; mock it so tests can control
// the job state without a real API layer. A real QueryClient is still needed
// -- the hook now calls useQueryClient() to invalidate the scores key on
// completion (see the "eval completion: scores refetch" describe below).
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

function renderLifecycle({ selectedProject = null, selectProjectAndRun = vi.fn(), client } = {}) {
  const queryClient = client || new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  const utils = renderHook(
    () =>
      useEvaluationLifecycle({
        settings: {},
        navigation: { navTab: vi.fn(), navReset: vi.fn() },
        projects: {
          loadProjects: vi.fn().mockResolvedValue([]),
          setProjects: vi.fn(),
          selectProjectAndRun,
        },
        selectedProject,
      }),
    { wrapper: ({ children }) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider> },
  );
  return { ...utils, queryClient };
}

describe("useEvaluationLifecycle background completion", () => {
  beforeEach(() => {
    evaluationState.job = null;
    evaluationState.jobError = null;
    evaluationState.startEvaluation = vi.fn();
  });

  it("does not switch the selection when another project's run finishes", () => {
    // Regression: a background eval finishing on project A yanked a user
    // viewing project B to A's data, without a nav reset.
    evaluationState.job = {
      jobId: "j-done", status: "done",
      outputProject: "project-a", outputRunId: "run-a1",
    };
    const selectProjectAndRun = vi.fn();
    renderLifecycle({ selectedProject: "project-b", selectProjectAndRun });
    expect(selectProjectAndRun).not.toHaveBeenCalled();
  });

  it("selects the finished run when it belongs to the viewed project", () => {
    evaluationState.job = {
      jobId: "j-done", status: "done",
      outputProject: "project-b", outputRunId: "run-b1",
    };
    const selectProjectAndRun = vi.fn();
    renderLifecycle({ selectedProject: "project-b", selectProjectAndRun });
    expect(selectProjectAndRun).toHaveBeenCalledWith("project-b", "run-b1");
  });

  it("adopts the finished run when no project is selected", () => {
    // First-eval onboarding: nothing selected yet, so showing the fresh
    // results is what the user expects.
    evaluationState.job = {
      jobId: "j-done", status: "done",
      outputProject: "project-a", outputRunId: "run-a1",
    };
    const selectProjectAndRun = vi.fn();
    renderLifecycle({ selectedProject: null, selectProjectAndRun });
    expect(selectProjectAndRun).toHaveBeenCalledWith("project-a", "run-a1");
  });
});

describe("handleEvalDismiss('view') cross-project jump", () => {
  beforeEach(() => {
    evaluationState.job = null;
    evaluationState.jobError = null;
    evaluationState.startedProject = null;
  });

  it("jumps to the evaluated project when another project is selected", () => {
    // The completion effect leaves the selection alone on purpose; the
    // view-results button is the explicit way to cross projects.
    evaluationState.job = {
      jobId: "j-done", status: "done",
      outputProject: "project-a", outputRunId: "run-a1",
    };
    const selectProjectAndRun = vi.fn();
    const { result } = renderLifecycle({ selectedProject: "project-b", selectProjectAndRun });
    expect(selectProjectAndRun).not.toHaveBeenCalled();
    act(() => result.current.handleEvalDismiss("view"));
    expect(selectProjectAndRun).toHaveBeenCalledWith("project-a", "run-a1");
  });

  it("does not reselect when already on the evaluated project", () => {
    evaluationState.job = {
      jobId: "j-done", status: "done",
      outputProject: "project-b", outputRunId: "run-b1",
    };
    const selectProjectAndRun = vi.fn();
    const { result } = renderLifecycle({ selectedProject: "project-b", selectProjectAndRun });
    // Once from the completion effect; the dismiss must not re-mint keys.
    expect(selectProjectAndRun).toHaveBeenCalledTimes(1);
    act(() => result.current.handleEvalDismiss("view"));
    expect(selectProjectAndRun).toHaveBeenCalledTimes(1);
  });

  it("falls back to the started project when the job never resolved one", () => {
    evaluationState.job = { jobId: "j-done", status: "done", outputProject: null, outputRunId: null };
    evaluationState.startedProject = "project-c";
    const selectProjectAndRun = vi.fn();
    const { result } = renderLifecycle({ selectedProject: "project-b", selectProjectAndRun });
    act(() => result.current.handleEvalDismiss("view"));
    expect(selectProjectAndRun).toHaveBeenCalledWith("project-c", null);
  });
});

// Finding 1 (P5 final review): removing useAppState's dashboard-key refetch
// (69b67347) orphaned the scores side. projectKeys.scores(project, null,
// source) -- the `latest` query behind useProjectScores's `accumulated` and
// `availableRuns` -- never changes key when selectedRun flips to the new
// run, so nothing refetched it: repeat-run projects showed stale grades
// until a tab round-trip, and first-run projects never got `accumulated` at
// all (contentReady stuck false, page stuck on the inline loader).
describe("useEvaluationLifecycle background completion: scores refetch", () => {
  beforeEach(() => {
    evaluationState.job = null;
    evaluationState.jobError = null;
    evaluationState.startEvaluation = vi.fn();
  });

  it("invalidates the completed project's local scores query on completion", () => {
    evaluationState.job = {
      jobId: "j-done", status: "done",
      outputProject: "project-a", outputRunId: "run-a1",
    };
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
    });
    const spy = vi.spyOn(client, "invalidateQueries");
    renderLifecycle({ selectedProject: "project-a", client });

    expect(spy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: projectKeys.scores("project-a", null, "local") }),
    );
    // The Compare fleet row for the finished project must refresh too.
    expect(spy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: projectKeys.compareSummary("project-a", "local") }),
    );
  });

  it("invalidates the scores query even when the finished project is not the one currently viewed", () => {
    // Unconditional on outputProject: a mark-stale/no-op invalidation of an
    // inactive observer's query is harmless, and this is the only path back
    // to fresh data for the Overview if the user switches to that project
    // later without a round-trip through another tab.
    evaluationState.job = {
      jobId: "j-done", status: "done",
      outputProject: "project-a", outputRunId: "run-a1",
    };
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
    });
    const spy = vi.spyOn(client, "invalidateQueries");
    renderLifecycle({ selectedProject: "project-b", client });

    expect(spy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: projectKeys.scores("project-a", null, "local") }),
    );
  });
});

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
