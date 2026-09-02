/**
 * useEvaluation — evaluation lifecycle hook backed by TanStack Query.
 *
 * Exposes:
 *   { job, jobError, liveViolations, startEvaluation, clearJob, cancelEvaluation }
 *
 * Data sources:
 *   - statusQuery: ['evaluation', jobId, 'status'] — fetched via api.getEvaluation
 *     and updated by useRunEventStream when VITE_USE_SSE_EVENTS=true.
 *   - findingsQuery: ['evaluation', jobId, 'findings'] — under SSE, populated
 *     entirely by useRunEventStream's setQueryData writes (queryFn is a no-op).
 *     Under polling, fetched via per-dimension getDimensionEval calls.
 *   (both live in ./useEvaluationQueries.js)
 *
 * Mutations (./useEvaluationMutations.js):
 *   - startMutation: api.startEvaluation -> seeds status cache on success.
 *   - cancelMutation: api.cancelEvaluation -> invalidates the run subtree.
 *
 * Mount-time auto-resume (useResumeRunningJob below):
 *   - On mount, calls api.listEvaluations({ states: ["running"] }) and adopts
 *     the most recent running job. Lets a `quodeq evaluate` started in the
 *     terminal surface in the dashboard so users can close and reopen the UI
 *     without losing visibility into an in-progress scan.
 */
import { useCallback, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useApi } from "../../../api/ApiContext.jsx";
import { confirmCancelEvaluation } from "../cancelDialog.js";
import { useRunEventStream } from "./useRunEventStream.js";
import { evaluationKeys } from "../../../api/queryKeys.js";
import { LOCAL_API_PROVIDERS } from "../../../constants.js";
import { findingsRefetchInterval } from "./useEvaluation.helpers.js";
import { useEvaluationQueries } from "./useEvaluationQueries.js";
import { useEvaluationMutations } from "./useEvaluationMutations.js";

export { findingsRefetchInterval };
// Re-exported for the existing importers; the set itself lives in constants.js
// so the Evaluate header resolves unset limits exactly like the start payload.
export { LOCAL_API_PROVIDERS };

// Adopt any in-progress CLI-started external run on mount so it surfaces on
// the Evaluate tab. setJobId's functional-update guard prevents a
// late-resolving resume from clobbering a job the user started meanwhile.
function useResumeRunningJob(api, queryClient, setJobId) {
  useEffect(() => {
    let cancelled = false;
    api.listEvaluations({ states: ["running"], limit: 1 })
      .then((jobs) => {
        if (cancelled) return;
        const running = jobs?.[0];
        if (!running) return;
        setJobId((current) => {
          if (current) return current;
          queryClient.setQueryData(evaluationKeys.status(running.jobId), running);
          return running.jobId;
        });
      })
      .catch((err) => {
        console.warn("Failed to fetch running evaluations:", err);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount-only resume
  }, []);
}

// The confirmation UI lives in ../cancelDialog.js (view layer); the hook
// only owns the business rule: which mutation to dispatch for a choice.
// `confirm` is injectable so a different presentation can drive the same
// rule. Guarded with a typeof check because callers commonly wire this
// straight to onClick, whose event argument must not shadow the default.
function useCancelEvaluationCallback(cancelMutation) {
  return useCallback(async (options) => {
    const confirm = typeof options?.confirm === "function"
      ? options.confirm
      : confirmCancelEvaluation;
    const choice = await confirm();
    if (!choice) return;
    cancelMutation.mutate({ discard: choice === "discard" });
  }, [cancelMutation]);
}

function useClearJobCallback(jobId, queryClient, setJobId, setJobError, setStartedProject) {
  return useCallback(() => {
    if (jobId) {
      // Drop cached entries so a future Start with a different jobId
      // doesn't carry stale findings/status into view (gcTime would
      // otherwise hold them for 5 minutes).
      queryClient.removeQueries({ queryKey: evaluationKeys.evaluation(jobId) });
    }
    setJobId(null);
    setJobError(null);
    setStartedProject(null);
  }, [jobId, queryClient]);
}

export function useEvaluation() {
  const api = useApi();
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState(null);
  const [jobError, setJobError] = useState(null);
  // Project id the current job was started for (UI-side). Bridges the gap
  // until the backend's report-path marker resolves job.outputProject, so
  // the in-progress card never has to guess from the global selection.
  const [startedProject, setStartedProject] = useState(null);

  // SSE side-effect — writes status/dimensions/findings into cache.
  // No-op when VITE_USE_SSE_EVENTS is off; refetchInterval below covers.
  useRunEventStream(jobId);
  useResumeRunningJob(api, queryClient, setJobId);

  const { job, liveViolations } = useEvaluationQueries(api, jobId);

  const { startMutation, cancelMutation } = useEvaluationMutations({
    api, queryClient, jobId, setJobId, setJobError, setStartedProject,
  });

  const startEvaluation = useCallback(
    (input) => startMutation.mutateAsync(input),
    [startMutation],
  );
  const cancelEvaluation = useCancelEvaluationCallback(cancelMutation);
  const clearJob = useClearJobCallback(jobId, queryClient, setJobId, setJobError, setStartedProject);

  return {
    job,
    jobError,
    liveViolations,
    startEvaluation,
    clearJob,
    cancelEvaluation,
    startedProject,
  };
}
