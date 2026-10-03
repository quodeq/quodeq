/**
 * useEvaluation's status/findings queries.
 *
 * See useEvaluation.js's header for the hook's overall data-flow doc.
 *
 * The findings query is subscribe-only. useRunEventStream writes every
 * admitted `finding` frame into its cache slot and this hook groups what is
 * there. There is no polled fallback for findings: the REST live-findings
 * path was a second implementation of "which judgments are findings" that
 * nothing ran under the default build, and the two drifted (#1383). The
 * server decides what a finding is, once, on the stream.
 */
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { NO_JOB_ID, evaluationKeys } from "../../../api/queryKeys.js";
import { statusRefetchInterval } from "./useEvaluation.helpers.js";

// The rows the cache already holds, per dimension, in cache order.
function groupFindingsByDimension(findings) {
  const liveViolations = {};
  for (const f of findings) {
    const dim = f.dimension || "_";
    (liveViolations[dim] ??= []).push(f);
  }
  return liveViolations;
}

// The slot is never fetched (enabled: false below): the stream fills it with
// setQueryData and useQuery is here for its subscription only, the same way
// useHistoryRunLive reads it. A fetch that resolved to [] after the first
// frame landed would wipe that frame.
const NEVER_QUERIED = () => {
  throw new Error("findings slot is stream-fed; queryFn must not run");
};

/**
 * The job status and its findings, grouped by dimension.
 *
 * @param {string} [streamState] the run's STREAM_STATE, from useRunEventStream
 * @returns {{job: object|null, liveViolations: Record<string, object[]>}}
 */
export function useEvaluationQueries(api, jobId, streamState) {
  // --- Status (the "job" object) ---------------------------------------
  const statusQuery = useQuery({
    queryKey: evaluationKeys.status(jobId || NO_JOB_ID),
    queryFn: () => api.getEvaluation(jobId),
    enabled: !!jobId,
    staleTime: Infinity,
    refetchInterval: statusRefetchInterval(streamState),
  });

  const job = statusQuery.data || null;

  // --- Findings (a flat list, then grouped into liveViolations) --------
  const findingsQuery = useQuery({
    queryKey: evaluationKeys.findings(jobId || NO_JOB_ID),
    queryFn: NEVER_QUERIED,
    enabled: false,
    staleTime: Infinity,
  });

  // Keyed on the query data, which React Query keeps by reference while the
  // rows are unchanged. A fresh object on every render would defeat the memos
  // in the stat strip and the live feed, which compare this by identity.
  const findings = findingsQuery.data;
  const liveViolations = useMemo(() => groupFindingsByDimension(findings || []), [findings]);

  return { job, liveViolations };
}
