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
import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useApi } from "../../../api/ApiContext.jsx";
import { confirmCancelEvaluation } from "../cancelDialog.js";
import { useRunEventStream } from "./useRunEventStream.js";
import { evaluationKeys, projectKeys } from "../../../api/queryKeys.js";
import {
  ACTIVE_PROVIDER_KEY,
  providerKey,
  LOCAL_API_PROVIDERS,
} from "../../../constants.js";
import { resolveProviderSettings } from "../../../utils/effectiveProviderSettings.js";
import { t } from "../../../strings/index.js";

const SSE_ENABLED = import.meta.env?.VITE_USE_SSE_EVENTS === "true";
const JOB_POLL_MS = 1500;
const DIM_POLL_MS = 2000;

/**
 * Poll interval for the live findings query. Exported for tests.
 *
 * Polling must stop once the job is terminal: without the gate a finished
 * run kept re-fetching every full evaluation/<dim>.json payload every 2s
 * for as long as the Evaluate card stayed mounted.
 */
export function findingsRefetchInterval(job, sseEnabled = SSE_ENABLED) {
  if (sseEnabled) return false;
  if (job?.status && job.status !== "running") return false;
  return DIM_POLL_MS;
}
// Re-exported for the existing importers; the set itself lives in constants.js
// so the Evaluate header resolves unset limits exactly like the start payload.
export { LOCAL_API_PROVIDERS };

/**
 * Merge per-provider Settings (provider, model, subagents, budget, etc.)
 * from localStorage into the start-evaluation payload.
 *
 * Caller-provided values win: a wizard launch names its provider/model and
 * time limit explicitly, and those must not be silently overwritten by the
 * active tab's Settings (the wizard's TIME LIMIT field used to be dead
 * code because of exactly that). Per-provider settings are read from the
 * payload's provider when one is named. Unset keys resolve through
 * resolveProviderSettings — the same source of truth the Settings screen
 * and the Evaluate header display. Throws a user-facing error if no
 * provider/model is configured.
 */
/**
 * An error whose message is meant for the user, not the console.
 *
 * The flag is what makes it safe to translate: the mutation's onError used
 * to decide by sniffing the message text (`msg.startsWith("No ")`), which
 * silently stops matching the moment the copy is translated or reworded.
 */
function userFacingError(key) {
  const err = new Error(t(key));
  err.userFacing = true;
  return err;
}

function preparePayload(payload, storage = localStorage) {
  const provider = payload.aiCmd || storage.getItem(ACTIVE_PROVIDER_KEY) || "";
  if (!provider) throw userFacingError("evaluate.noProviderSelected");
  const get = (key) => storage.getItem(providerKey(provider, key));
  const model = payload.aiModel || get("model");
  if (!model) throw userFacingError("evaluate.noModelSelected");
  const settings = resolveProviderSettings(provider, storage);
  const result = {
    ...payload,
    aiCmd: provider,
    aiModel: model,
    maxSubagents: settings.subagents,
    timeLimit: payload.timeLimit ?? settings.timeLimitS,
  };
  if (settings.perDimension) result.perDimension = true;
  if (!settings.verify) result.verifyFindings = false;
  const apiKey = get("api-key");
  if (apiKey) result.apiKey = apiKey;
  const apiBase = get("api-base");
  if (apiBase) result.apiBase = apiBase;
  return result;
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
            // Tolerate not-yet-written dimension evals during live polling,
            // but leave a diagnostic so a real fetch failure is visible.
            .catch((err) => {
              console.warn(`Failed to fetch ${d} evaluation:`, err);
              return [];
            }),
        ),
      );
      return results.flat();
    },
    enabled: !!jobId && (SSE_ENABLED || !!job?.outputProject),
    staleTime: SSE_ENABLED ? Infinity : 0,
    refetchInterval: findingsRefetchInterval(job),
  });

  // One final fetch on the running->terminal edge: the last dimension's
  // report usually lands between the final running poll and the terminal
  // transition, and stopping cold would freeze the feed just short of it.
  const { refetch: refetchFindings } = findingsQuery;
  const findingsSettledRef = useRef(false);
  const isJobTerminal = !!job?.status && job.status !== "running";
  useEffect(() => {
    if (!jobId || SSE_ENABLED) return;
    if (isJobTerminal && !findingsSettledRef.current) {
      findingsSettledRef.current = true;
      refetchFindings();
    } else if (!isJobTerminal) {
      findingsSettledRef.current = false;
    }
  }, [jobId, isJobTerminal, refetchFindings]);

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
      // uiProject is client-side bookkeeping (which project launched this
      // job) — strip it so it never reaches the HTTP payload.
      const { uiProject, ...rest } = input;
      // preparePayload throws on missing provider/model — let the error
      // propagate to onError so jobError gets set with a useful message.
      const prepared = preparePayload(rest);
      return api.startEvaluation(prepared).then((created) => ({
        ...created,
        repo: prepared.repo,
        uiProject,
      }));
    },
    onSuccess: (created) => {
      setJobError(null);
      setJobId(created.jobId);
      setStartedProject(created.uiProject || null);
      queryClient.setQueryData(evaluationKeys.status(created.jobId), created);
      // Invalidate the project subtree so History (and any other view
      // backed by project queries) shows the freshly-started run as
      // 'running' immediately, instead of waiting for the next poll
      // tick. Without this, History stays stale until the user
      // navigates away and back, or the polling timer fires --
      // user-visible delay was ~10-30s on a fresh start.
      queryClient.invalidateQueries({ queryKey: projectKeys.all() });
    },
    onError: (err) => {
      // Only our own prereq errors carry copy worth showing; anything else
      // is a transport/server failure whose raw text would be noise.
      setJobError(err?.userFacing ? err.message : t("evaluate.startFailed"));
    },
  });

  const cancelMutation = useMutation({
    mutationFn: ({ discard } = {}) => api.cancelEvaluation(jobId, { discard }),
    onSuccess: (_data, variables) => {
      if (variables?.discard) {
        // Discard deletes the run server-side (dir + index row + job
        // entry), so any further status poll would 404. Drop the job and
        // its cached queries right away instead of waiting for a terminal
        // status that will never arrive.
        if (jobId) {
          queryClient.removeQueries({ queryKey: evaluationKeys.evaluation(jobId) });
        }
        setJobId(null);
        setStartedProject(null);
      } else if (jobId) {
        queryClient.invalidateQueries({ queryKey: evaluationKeys.evaluation(jobId) });
      }
      // Mirror startMutation: refresh the project subtree so History's
      // availableRuns drops the cancelled run from the in-progress list
      // immediately. Without this, the History row stays on the
      // 'performing an evaluation...' placeholder until the next polling
      // tick (or, under SSE, the terminal-status event from the stream).
      queryClient.invalidateQueries({ queryKey: projectKeys.all() });
    },
    onError: (err) => {
      // The backend returns 409 when the job is no longer cancellable
      // (process gone, status already terminal) and 404 when it is unknown.
      // Only those mean the job is really over — clear it so the panel
      // closes. A transient failure (500, network, the 30s request timeout
      // racing the ~33s server-side kill path) must KEEP the job: clearing
      // it hid a still-running scan and let a second concurrent scan start
      // on the same project.
      // Keep the backend's sentence as a detail suffix: a 409 ("already
      // finished") and a 500 are different situations for the user, and the
      // translated summary alone flattened them into one. Same policy as
      // apiErrorMessage, which preserves err.message for unmapped codes.
      setJobError(err?.message ? `${t("evaluate.cancelFailed")} (${err.message})` : t("evaluate.cancelFailed"));
      if (err?.status !== 409 && err?.status !== 404) return;
      const id = jobId;
      if (id) queryClient.removeQueries({ queryKey: evaluationKeys.evaluation(id) });
      setJobId(null);
    },
  });

  const startEvaluation = useCallback(
    (input) => startMutation.mutateAsync(input),
    [startMutation],
  );

  // The confirmation UI lives in ../cancelDialog.js (view layer); the hook
  // only owns the business rule: which mutation to dispatch for a choice.
  // `confirm` is injectable so a different presentation can drive the same
  // rule. Guarded with a typeof check because callers commonly wire this
  // straight to onClick, whose event argument must not shadow the default.
  const cancelEvaluation = useCallback(async (options) => {
    const confirm = typeof options?.confirm === "function"
      ? options.confirm
      : confirmCancelEvaluation;
    const choice = await confirm();
    if (!choice) return;
    cancelMutation.mutate({ discard: choice === "discard" });
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
    setStartedProject(null);
  }, [jobId, queryClient]);

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
