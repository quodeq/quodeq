/**
 * useEvaluation's status/findings queries.
 *
 * Split out of useEvaluation.js (see that file's header for the hook's
 * overall data-flow doc). Moved verbatim: the SSE_ENABLED branches here are
 * unchanged from the pre-split version. queryFn/effect/grouping bodies are
 * additionally factored into named functions (still logic-identical) so
 * useEvaluationQueries itself clears the max-lines-per-function gate.
 */
import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { evaluationKeys } from "../../../api/queryKeys.js";
import { SSE_ENABLED, findingsRefetchInterval } from "./useEvaluation.helpers.js";

const JOB_POLL_MS = 1500;

// Under SSE the cache is filled by useRunEventStream; this queryFn is a
// no-op. Under polling, fetch each dimension's eval and flatten violations.
async function fetchFindings(api, job) {
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
}

// One final fetch on the running->terminal edge: the last dimension's
// report usually lands between the final running poll and the terminal
// transition, and stopping cold would freeze the feed just short of it.
function useTerminalFindingsRefetch(jobId, isJobTerminal, refetchFindings) {
  const findingsSettledRef = useRef(false);
  useEffect(() => {
    if (!jobId || SSE_ENABLED) return;
    if (isJobTerminal && !findingsSettledRef.current) {
      findingsSettledRef.current = true;
      refetchFindings();
    } else if (!isJobTerminal) {
      findingsSettledRef.current = false;
    }
  }, [jobId, isJobTerminal, refetchFindings]);
}

// Group findings into the legacy { [dim]: [violations] } shape.
function groupFindingsByDimension(findings) {
  const liveViolations = {};
  for (const f of findings) {
    const dim = f.dimension || "_";
    (liveViolations[dim] ??= []).push(f);
  }
  return liveViolations;
}

export function useEvaluationQueries(api, jobId) {
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
  const findingsQuery = useQuery({
    queryKey: jobId ? evaluationKeys.findings(jobId) : ["evaluation", "_none_", "findings"],
    queryFn: () => fetchFindings(api, job),
    enabled: !!jobId && (SSE_ENABLED || !!job?.outputProject),
    staleTime: SSE_ENABLED ? Infinity : 0,
    refetchInterval: findingsRefetchInterval(job),
  });

  const isJobTerminal = !!job?.status && job.status !== "running";
  useTerminalFindingsRefetch(jobId, isJobTerminal, findingsQuery.refetch);

  const liveViolations = groupFindingsByDimension(findingsQuery.data || []);

  return { job, liveViolations };
}
