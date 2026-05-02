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
 * Mount-time auto-resume:
 *   - On mount, calls api.listEvaluations({ states: ["running"] }) and adopts
 *     the most recent running job. Lets a `quodeq evaluate` started in the
 *     terminal surface in the dashboard so users can close and reopen the UI
 *     without losing visibility into an in-progress scan.
 */
import { useCallback, useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useApi } from "../../../api/ApiContext.jsx";
import { confirmDialog } from "../../../utils/confirmDialog.js";
import { useRunEventStream } from "./useRunEventStream.js";
import { evaluationKeys } from "../../../api/queryKeys.js";
import {
  ACTIVE_PROVIDER_KEY,
  providerKey,
  DEFAULT_MAX_SUBAGENTS,
  DEFAULT_POOL_BUDGET,
} from "../../../constants.js";

const SSE_ENABLED = import.meta.env?.VITE_USE_SSE_EVENTS === "true";
const JOB_POLL_MS = 1500;
const DIM_POLL_MS = 2000;
const DEFAULT_OLLAMA_SUBAGENTS = "1";
const DEFAULT_CLI_SUBAGENTS = String(DEFAULT_MAX_SUBAGENTS);
const DEFAULT_OLLAMA_BUDGET = "0";
const DEFAULT_CLI_BUDGET = String(DEFAULT_POOL_BUDGET);

/**
 * Merge per-provider Settings (provider, model, subagents, budget, etc.)
 * from localStorage into the start-evaluation payload. Mirrors the legacy
 * useEvaluation behavior; throws a user-facing error if no provider/model
 * is configured.
 */
function preparePayload(payload, storage = localStorage) {
  const activeProvider = storage.getItem(ACTIVE_PROVIDER_KEY) || "";
  if (!activeProvider) throw new Error("No provider selected. Go to Settings to configure one.");
  const get = (key) => storage.getItem(providerKey(activeProvider, key));
  const model = get("model");
  if (!model) throw new Error("No model selected. Go to Settings and select one.");
  const isOllama = activeProvider === "ollama";
  const subagents = parseInt(get("subagents") || (isOllama ? DEFAULT_OLLAMA_SUBAGENTS : DEFAULT_CLI_SUBAGENTS), 10);
  const poolBudget = parseInt(get("pool-budget") || (isOllama ? DEFAULT_OLLAMA_BUDGET : DEFAULT_CLI_BUDGET), 10);
  const result = {
    ...payload,
    aiCmd: activeProvider,
    aiModel: model,
    maxSubagents: subagents,
    poolBudget,
  };
  if (get("per-dimension") === "true") result.perDimension = true;
  if (get("verify") === "false") result.verifyFindings = false;
  return result;
}

export function useEvaluation() {
  const api = useApi();
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState(null);
  const [jobError, setJobError] = useState(null);

  // SSE side-effect — writes status/dimensions/findings into cache.
  // No-op when VITE_USE_SSE_EVENTS is off; refetchInterval below covers.
  useRunEventStream(jobId);

  // Adopt any in-progress CLI-started external run on mount so it surfaces
  // on the Evaluate tab. setJobId guard prevents a late-resolving resume
  // from clobbering a job the user started in the meantime.
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
    mutationFn: (input) => {
      // preparePayload throws on missing provider/model — let the error
      // propagate to onError so jobError gets set with a useful message.
      const prepared = preparePayload(input);
      return api.startEvaluation(prepared).then((created) => ({
        ...created,
        repo: prepared.repo,
      }));
    },
    onSuccess: (created) => {
      setJobError(null);
      setJobId(created.jobId);
      queryClient.setQueryData(evaluationKeys.status(created.jobId), created);
    },
    onError: (err) => {
      const msg = err?.message || "Failed to start evaluation.";
      setJobError(
        msg.startsWith("No ") || msg.startsWith("Select ") ? msg : "Failed to start evaluation",
      );
    },
  });

  const cancelMutation = useMutation({
    mutationFn: ({ discard } = {}) => api.cancelEvaluation(jobId, { discard }),
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
    const result = await confirmDialog({
      title: "Cancel evaluation?",
      message: "The run will stop. Findings collected so far are kept by default.",
      checkboxLabel: "Discard collected findings",
      confirmLabel: "Cancel evaluation",
      cancelLabel: "Keep running",
      variant: "danger",
    });
    if (!result || !result.ok) return;
    cancelMutation.mutate({ discard: result.checked });
  }, [cancelMutation]);

  const clearJob = useCallback(() => {
    if (jobId) {
      // Drop cached entries so a future Start with a different jobId
      // doesn't carry stale findings/status into view (gcTime would
      // otherwise hold them for 5 minutes).
      queryClient.removeQueries({ queryKey: evaluationKeys.evaluation(jobId) });
    }
    setJobId(null);
    setJobError(null);
  }, [jobId, queryClient]);

  return {
    job,
    jobError,
    liveViolations,
    startEvaluation,
    clearJob,
    cancelEvaluation,
  };
}
