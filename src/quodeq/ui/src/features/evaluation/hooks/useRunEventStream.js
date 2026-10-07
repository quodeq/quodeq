/**
 * SSE → cache-update writer.
 *
 * Subscribes to /api/evaluations/<jobId>/events and writes each event
 * into the TanStack Query cache via setQueryData. Components consume
 * the cached data via useQuery, agnostic to whether it arrived via
 * initial GET, refetchInterval poll, or this SSE handler.
 *
 * Returns the stream's connection state (STREAM_STATE), so the polling
 * policy can fall back to a fast poll while the stream is down. The
 * EventSource itself is shared per run via runEventSourceRegistry: any
 * number of subscribers to the same run hold one connection.
 *
 * Each cache write is preceded by a fire-and-forget cancelQueries on
 * the same key. This prevents an in-flight initial fetch (or poll)
 * from landing AFTER our setQueryData and overwriting the streamed
 * value — a real race once a query is mounted in the same render as
 * the SSE handler.
 */
import { useCallback, useEffect, useSyncExternalStore } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { evaluationKeys, isRunQueryKey, projectKeys } from "../../../api/queryKeys.js";
import { createViolation } from "../../../models/violation.js";
import { applyStatusFrame } from "../../../models/job.js";
import { JOB_FINISHED } from "../../../vocab/jobStatus.js";
import { SSE_EVENT } from "../../../vocab/sseEvent.js";
import {
  acquireRunStream, getRunStreamState, subscribeRunStream,
} from "./runEventSourceRegistry.js";

// Cap the per-job findings array so a long-running scan with tens of thousands
// of findings does not grow the React Query cache without bound. The dashboard
// renders aggregated counts and the most-recent slice; older entries are still
// reachable through the scored evaluation/<dim>.json artifacts on disk.
const MAX_FINDINGS_IN_CACHE = 5000;
// How far past the cap the array may run before it is cut back. Dropping one
// row per event shifts every held row by one, and the cache's structural
// sharing then deep-compares all of them against their neighbours: ~2 ms per
// finding on a full cache, seconds of frozen UI for a replayed run. Cutting a
// block at a time pays that once per block instead.
const FINDINGS_TRIM_SLACK = 1000;

// Findings are written to the cache in batches, at most one write per this
// many ms. Every write regroups the list and re-renders the feed, and a
// replayed run delivers thousands of frames back to back.
export const FINDINGS_FLUSH_MS = 100;
// EventSource.CLOSED. A closed source's pending rows are dropped: the next
// connection replays the run from its first event.
const SOURCE_CLOSED = 2;

// Each row is stamped with its place in the stream. The feed's per-dimension
// grouping loses the order across dimensions, and the live ticker needs it to
// show the latest findings whichever dimension they came from.
function appendBoundedFindings(prev, findings) {
  let seq = prev.at(-1)?.arrivalSeq ?? 0;
  const stamped = findings.map((f) => ({ ...f, arrivalSeq: ++seq }));
  const total = prev.length + stamped.length;
  if (total > MAX_FINDINGS_IN_CACHE + FINDINGS_TRIM_SLACK) {
    return [...prev, ...stamped].slice(total - MAX_FINDINGS_IN_CACHE);
  }
  return [...prev, ...stamped];
}

// A dimension just scored. The run's own pages (opened from a running
// History row) are not polled under SSE and stay fresh for a staleTime, so
// it would not show up there. Mark them stale: a mounted run page refetches
// now, an unmounted one on its next open.
// The stream is opened either with a job id (Evaluate), whose cached job
// names the run it writes, or with the run id itself (History rows).
function invalidateRunQueries(queryClient, jobId) {
  const runId = queryClient.getQueryData(evaluationKeys.status(jobId))?.outputRunId || jobId;
  queryClient.invalidateQueries({ predicate: (query) => isRunQueryKey(query.queryKey, runId) });
}

// Holds finding frames and writes them to the cache together, one write per
// FINDINGS_FLUSH_MS at most. `flush` lands whatever is pending right away.
function createFindingBatcher({ source, jobId, writeCache }) {
  let pending = [];
  let timer = null;
  const flush = () => {
    clearTimeout(timer);
    timer = null;
    const batch = pending;
    pending = [];
    if (!batch.length || source.readyState === SOURCE_CLOSED) return;
    writeCache(evaluationKeys.findings(jobId), (prev) => appendBoundedFindings(prev ?? [], batch));
  };
  const push = (finding) => {
    pending.push(finding);
    timer ??= setTimeout(flush, FINDINGS_FLUSH_MS);
  };
  return { push, flush };
}

function wireRunEventSource({ source, finish, jobId, writeCache, queryClient }) {
  const findings = createFindingBatcher({ source, jobId, writeCache });

  source.addEventListener(SSE_EVENT.STATUS, (e) => {
    try {
      // The frame is the raw snake_case status.json, whose `state` is a
      // RunState. Normalise onto the cached REST job so every reader sees
      // one Job shape (EvaluationStatus used to render a raw frame as
      // "cancelled" because `job.status` was undefined).
      const frame = JSON.parse(e.data);
      let job;
      writeCache(evaluationKeys.status(jobId), (prev) => {
        job = applyStatusFrame(prev, frame);
        return job;
      });
      if (job && JOB_FINISHED.has(job.status)) {
        // Run just hit a terminal state -- the trend's view of this run is
        // about to flip from "in-progress / partial" to "terminal / final".
        // Invalidate the project subtree so the History row rerenders against
        // the freshly-fetched trend instead of staying on the SSE-fed live
        // dim cache for an unbounded time.
        queryClient.invalidateQueries({ queryKey: projectKeys.all() });
      }
    } catch (err) {
      // malformed frame; reconnect handles recovery via Last-Event-ID
      console.warn("[useRunEventStream] could not parse status frame:", err);
    }
  });

  source.addEventListener(SSE_EVENT.DIMENSION_COMPLETED, (e) => {
    try {
      const data = JSON.parse(e.data);
      writeCache(
        evaluationKeys.dimensions(jobId),
        (prev = {}) => ({ ...prev, [data.dimension]: data }),
      );
      invalidateRunQueries(queryClient, jobId);
    } catch (err) {
      console.warn("[useRunEventStream] could not parse dimension-completed frame:", err);
    }
  });

  source.addEventListener(SSE_EVENT.FINDING, (e) => {
    try {
      // Normalised on the way in, so the cache holds one shape whichever
      // path filled it. The frame is snake_case straight off the payload
      // (practice_id, carried_forward), unlike the REST paths. Merged onto
      // the raw frame rather than replacing it, so id/verdict/confidence,
      // which the model does not carry, survive for other readers.
      const raw = JSON.parse(e.data);
      findings.push({ ...raw, ...createViolation(raw) });
    } catch (err) {
      console.warn("[useRunEventStream] could not parse finding frame:", err);
    }
  });

  // Pending findings land before the run reads as finished.
  source.addEventListener(SSE_EVENT.DONE, () => { findings.flush(); finish(); });
}

/**
 * Subscribes to a run's SSE stream and writes status, dimensions and findings
 * straight into the query caches, so the screens reading those keys update
 * without polling.
 *
 * No-op when the job id is absent. The shared stream is released on unmount
 * (closed once its last subscriber goes) and closed for good when the run
 * finishes.
 *
 * @returns {string} the stream's STREAM_STATE
 */
export function useRunEventStream(jobId) {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!jobId) return undefined;

    const writeCache = (key, updater) => {
      // Fire-and-forget by design (see file-level comment): the setQueryData
      // write below must not wait on the cancel. Still log a rejection
      // instead of letting it vanish as an unhandled promise rejection.
      queryClient.cancelQueries({ queryKey: key }).catch((err) => {
        console.warn('[useRunEventStream] cancelQueries failed:', err);
      });
      queryClient.setQueryData(key, updater);
    };

    return acquireRunStream(queryClient, jobId, (source, finish) => {
      // A new connection replays the run from its first event, so the
      // findings list restarts with it. Appending the replay onto rows a
      // previous connection left behind duplicated all of them (History
      // opens a connection per visit).
      queryClient.setQueryData(evaluationKeys.findings(jobId), (prev) => (prev?.length ? [] : prev));
      wireRunEventSource({ source, finish, jobId, writeCache, queryClient });
    });
  }, [jobId, queryClient]);

  const subscribe = useCallback(
    (onChange) => subscribeRunStream(queryClient, jobId, onChange),
    [queryClient, jobId],
  );
  const getSnapshot = useCallback(
    () => getRunStreamState(queryClient, jobId),
    [queryClient, jobId],
  );
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}
