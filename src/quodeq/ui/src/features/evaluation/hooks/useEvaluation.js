/**
 * useEvaluation — evaluation lifecycle hook backed by TanStack Query.
 *
 * Exposes:
 *   { job, jobError, liveViolations, startEvaluation, clearJob, cancelEvaluation }
 *
 * Data sources:
 *   - statusQuery: ['evaluation', jobId, 'status'] — fetched via api.getEvaluation
 *     and updated by useRunEventStream's status frames.
 *   - findingsQuery: ['evaluation', jobId, 'findings'] — populated entirely
 *     by useRunEventStream's setQueryData writes (queryFn is a no-op). The
 *     server decides which judgments are findings, once, on the stream.
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
import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useApi } from "../../../api/ApiContext.jsx";
import { apiErrorMessage } from "../../../strings/apiErrors.js";
import { confirmCancelEvaluation, CANCEL_CHOICE } from "../cancelDialog.js";
import { useRunEventStream } from "./useRunEventStream.js";
import { evaluationKeys } from "../../../api/queryKeys.js";
import { LOCAL_API_PROVIDERS } from "../../../vocab/provider.js";
import { useEvaluationQueries } from "./useEvaluationQueries.js";
import { useEvaluationMutations } from "./useEvaluationMutations.js";
import { ADOPT_POLL_MS } from "./useEvaluation.helpers.js";
import { JOB_SOURCE, JOB_TERMINAL } from "../../../vocab/jobStatus.js";

const HTTP_NOT_FOUND = 404;

// Re-exported for the existing importers; the set itself lives in vocab/provider.js
// so the Evaluate header resolves unset limits exactly like the start payload.
export { LOCAL_API_PROVIDERS };

// Adopt a run started outside the app (CLI, CI, MCP) so it surfaces on the
// Evaluate tab: once at mount, then every ADOPT_POLL_MS while nothing is
// held or the held run is over (a finished run left on screen must not hide
// the next nightly). A different running run then takes the held one's
// place. setJobId's functional guard keeps a late answer from clobbering a
// job the user started meanwhile. Only the mount check reports a failure as
// jobError: a CLI run could be in flight and the dashboard would otherwise
// show no trace of it.
function useResumeRunningJob({ api, queryClient, jobId, heldOver, setJobId, setJobError, setStartedProject }) {
  const jobIdRef = useRef(jobId);
  jobIdRef.current = jobId;
  const adopt = (onError) => api.listEvaluations({ states: ["running"], limit: 1 })
    .then((jobs) => {
      const running = jobs?.[0];
      const held = jobIdRef.current;
      if (!running || running.jobId === held) return;
      if (held && !isHeldJobOver(queryClient, held)) return;
      queryClient.setQueryData(evaluationKeys.status(running.jobId), running);
      setJobId((current) => (current && current !== held ? current : running.jobId));
      if (held) {
        queryClient.removeQueries({ queryKey: evaluationKeys.evaluation(held) });
        setStartedProject(null);
      }
    })
    .catch(onError);
  useEffect(() => {
    let cancelled = false;
    adopt((err) => {
      if (cancelled) return;
      console.warn("Failed to fetch running evaluations:", err);
      setJobError(apiErrorMessage(err, "evaluate.resumeFailed"));
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount-only check
  }, []);
  useEffect(() => {
    if (jobId && !heldOver) return undefined;
    const timer = setInterval(() => {
      adopt((err) => console.warn("[useEvaluation] running-run check failed:", err));
    }, ADOPT_POLL_MS);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- adopt reads stable handles
  }, [jobId, heldOver]);
}

// The held run is over: it reached a terminal state, or its status GET
// answers 404 (its folder vanished).
function isHeldJobOver(queryClient, jobId) {
  const key = evaluationKeys.status(jobId);
  return JOB_TERMINAL.has(queryClient.getQueryData(key)?.status)
    || queryClient.getQueryState(key)?.error?.status === HTTP_NOT_FOUND;
}

// The confirmation UI lives in ../cancelDialog.js (view layer); the hook
// only owns the business rule: which mutation to dispatch for a choice.
// `confirm` is injectable so a different presentation can drive the same
// rule. Guarded with a typeof check because callers commonly wire this
// straight to onClick, whose event argument must not shadow the default.
function useCancelEvaluationCallback(cancelMutation, job) {
  const external = job?.source === JOB_SOURCE.EXTERNAL;
  return useCallback(async (options) => {
    const confirm = typeof options?.confirm === "function"
      ? options.confirm
      : () => confirmCancelEvaluation(undefined, { external });
    const choice = await confirm();
    if (!choice) return;
    cancelMutation.mutate({ discard: choice === CANCEL_CHOICE.DISCARD });
  }, [cancelMutation, external]);
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

/**
 * The running evaluation: the job, its live findings grouped by dimension,
 * any error, and the start/cancel/dismiss handles.
 *
 * A job already running when the UI loads is picked back up, so a reload
 * never strands one. `startedProject` names the project the run was launched
 * for, which the in-progress card uses until the backend resolves the job's
 * own project.
 */
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
  // Its connection state drives the status query's poll interval.
  const streamState = useRunEventStream(jobId);
  const { job, liveViolations } = useEvaluationQueries(api, jobId, streamState);
  useResumeRunningJob({
    api, queryClient, jobId, heldOver: !!job && JOB_TERMINAL.has(job.status), setJobId, setJobError, setStartedProject,
  });

  const { startMutation, cancelMutation } = useEvaluationMutations({
    api, queryClient, jobId, setJobId, setJobError, setStartedProject,
  });

  const startEvaluation = useCallback(
    (input) => startMutation.mutateAsync(input),
    [startMutation],
  );
  const cancelEvaluation = useCancelEvaluationCallback(cancelMutation, job);
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
