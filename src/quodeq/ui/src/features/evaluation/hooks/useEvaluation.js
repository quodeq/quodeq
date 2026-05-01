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
 *
 * Mutations:
 *   - startMutation: api.startEvaluation -> seeds status cache on success.
 *   - cancelMutation: api.cancelEvaluation -> invalidates the run subtree.
 *
 * Out of scope (vs. legacy hook):
 *   - Auto-resume of CLI-started external runs via listEvaluations on mount.
 *     Restore in a follow-up if required by user reports.
 */
import { useCallback, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useApi } from "../../../api/ApiContext.jsx";
import { confirmDialog } from "../../../utils/confirmDialog.js";
import { useRunEventStream } from "./useRunEventStream.js";
import { evaluationKeys } from "../../../api/queryKeys.js";

const SSE_ENABLED = import.meta.env?.VITE_USE_SSE_EVENTS === "true";
const JOB_POLL_MS = 1500;
const DIM_POLL_MS = 2000;

export function useEvaluation() {
  const api = useApi();
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState(null);
  const [jobError, setJobError] = useState(null);

  // SSE side-effect — writes status/dimensions/findings into cache.
  // No-op when VITE_USE_SSE_EVENTS is off; refetchInterval below covers.
  useRunEventStream(jobId);

  // --- Status (the "job" object) ---------------------------------------
  const statusQuery = useQuery({
    queryKey: jobId ? evaluationKeys.status(jobId) : ["evaluation", "_none_", "status"],
    queryFn: () => api.getEvaluation(jobId),
    enabled: !!jobId,
    staleTime: SSE_ENABLED ? Infinity : 0,
    refetchInterval: SSE_ENABLED ? false : JOB_POLL_MS,
  });

  const job = statusQuery.data || null;

  // --- Findings (a flat list, then grouped into liveViolations) --------
  // Under SSE the cache is filled by useRunEventStream; queryFn is a no-op.
  // Under polling, fetch each dimension's eval and flatten violations.
  const findingsQuery = useQuery({
    queryKey: jobId ? evaluationKeys.findings(jobId) : ["evaluation", "_none_", "findings"],
    queryFn: async () => {
      if (SSE_ENABLED) return [];
      if (!job?.outputProject || !job?.outputRunId || !job?.dimensions?.length) {
        return [];
      }
      const results = await Promise.all(
        job.dimensions.map((d) =>
          api.getDimensionEval(job.outputProject, job.outputRunId, d)
            .then((data) => (data?.violations || []).map((v) => ({ ...v, dimension: d })))
            .catch(() => []),
        ),
      );
      return results.flat();
    },
    enabled: !!jobId && (SSE_ENABLED || !!job?.outputProject),
    staleTime: SSE_ENABLED ? Infinity : 0,
    refetchInterval: SSE_ENABLED ? false : DIM_POLL_MS,
  });

  // Group findings into the legacy { [dim]: [violations] } shape.
  const findings = findingsQuery.data || [];
  const liveViolations = {};
  for (const f of findings) {
    const dim = f.dimension || "_";
    (liveViolations[dim] ??= []).push(f);
  }

  // --- Mutations -------------------------------------------------------
  const startMutation = useMutation({
    mutationFn: (input) => api.startEvaluation(input),
    onSuccess: (created) => {
      setJobError(null);
      setJobId(created.jobId);
      queryClient.setQueryData(evaluationKeys.status(created.jobId), created);
    },
    onError: (err) => setJobError(err?.message || "Failed to start evaluation."),
  });

  const cancelMutation = useMutation({
    mutationFn: () => api.cancelEvaluation(jobId),
    onSuccess: () => {
      if (jobId) {
        queryClient.invalidateQueries({ queryKey: evaluationKeys.evaluation(jobId) });
      }
    },
  });

  const startEvaluation = useCallback(
    (input) => startMutation.mutateAsync(input),
    [startMutation],
  );

  const cancelEvaluation = useCallback(async () => {
    const ok = await confirmDialog("Cancel this evaluation?");
    if (!ok) return;
    cancelMutation.mutate();
  }, [cancelMutation]);

  const clearJob = useCallback(() => {
    setJobId(null);
    setJobError(null);
  }, []);

  return {
    job,
    jobError,
    liveViolations,
    startEvaluation,
    clearJob,
    cancelEvaluation,
  };
}
