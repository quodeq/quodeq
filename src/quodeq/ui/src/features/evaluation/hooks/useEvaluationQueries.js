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
import { useMemo, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { NO_JOB_ID, evaluationKeys } from "../../../api/queryKeys.js";
import { statusRefetchInterval } from "./useEvaluation.helpers.js";
import { JOB_STATUS } from "../../../vocab/jobStatus.js";

const HTTP_NOT_FOUND = 404;
const STATUS_RETRIES = 3;

// A 404 for a job already seen means its run is gone: a PR review's folder
// is deleted by the CI runner when the job ends. Not worth asking again.
function isGone(error) {
  return error?.status === HTTP_NOT_FOUND;
}

// The last state the job had, read as finished. DONE makes every consumer
// treat it as over without failure UI (no progress polling, no "tracking
// lost" banner); `vanished` lets the header say "ended", since how it
// really ended is unknown.
function vanishedJob(job) {
  return { ...job, status: JOB_STATUS.DONE, vanished: true };
}

// The rows the cache already holds, per dimension, in cache order.
function groupFindingsByDimension(findings) {
  const liveViolations = {};
  for (const f of findings) {
    const dim = f.dimension || "_";
    (liveViolations[dim] ??= []).push(f);
  }
  return liveViolations;
}

// The cache only appends (or cuts a block off the front), so a dimension with
// the same length and the same first and last row holds the same rows. Hand
// back its previous array then: the feed memoises each dimension on it, and a
// finding in one dimension would otherwise re-render and re-sort every other.
function keepUnchangedDimensions(next, prev) {
  for (const [dim, rows] of Object.entries(next)) {
    const old = prev[dim];
    if (old && old.length === rows.length && old[0] === rows[0] && old.at(-1) === rows.at(-1)) next[dim] = old;
  }
  return next;
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
    refetchInterval: (query) => (isGone(query.state.error) ? false : statusRefetchInterval(streamState)),
    retry: (count, error) => !isGone(error) && count < STATUS_RETRIES,
  });

  // React Query keeps the last good data through an error.
  const gone = !!statusQuery.data && isGone(statusQuery.error);
  const job = useMemo(
    () => (gone ? vanishedJob(statusQuery.data) : statusQuery.data || null),
    [gone, statusQuery.data],
  );

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
  const previous = useRef({});
  const liveViolations = useMemo(() => {
    const grouped = keepUnchangedDimensions(groupFindingsByDimension(findings || []), previous.current);
    previous.current = grouped;
    return grouped;
  }, [findings]);

  return { job, liveViolations };
}
