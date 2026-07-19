/**
 * Prefetch a single run's dashboard + scores payloads into the query cache.
 *
 * Pairs with the run-detail views: warming the cache on hover means that by
 * the time the user clicks, the data is often already there and the loading
 * state is skipped entirely. Shared by the overview run navigator
 * (usePrefetchAdjacentRuns) and the History table rows.
 *
 * The prefetch fires only after the pointer dwells PREFETCH_DWELL_MS on the
 * same run. Both payloads are expensive to build server-side (seconds of CPU
 * on large projects), so prefetching every row a mouse sweep crosses queued
 * enough work to stall the click's own requests for tens of seconds. A dwell
 * captures hover-then-click intent while a sweep across rows fires nothing:
 * each new run resets the shared timer, and cancelPrefetch drops the pending
 * one when the pointer leaves the rows entirely.
 */
import { useCallback, useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useApi } from "../../../api/ApiContext.jsx";
import { projectKeys } from "../../../api/queryKeys.js";

const STALE_TIME_MS = 60_000;
export const PREFETCH_DWELL_MS = 150;

/**
 * @param {string} selectedProject
 * @param {'local'|'shared'} [selectedSource='local'] - picks the shared-repo
 *   mirror fetchers (sharedGetDashboard/sharedGetProjectScores) instead of
 *   the local ones, and is folded into the cache keys so a source flip
 *   never warms/reads the other source's cache slot.
 */
export function usePrefetchRun(selectedProject, selectedSource = "local") {
  const queryClient = useQueryClient();
  const { getDashboard, sharedGetDashboard, getProjectScores, sharedGetProjectScores } = useApi();
  const fetchDashboard = selectedSource === "shared" ? sharedGetDashboard : getDashboard;
  const fetchScores = selectedSource === "shared" ? sharedGetProjectScores : getProjectScores;
  const timerRef = useRef(null);

  const cancelPrefetch = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  useEffect(() => cancelPrefetch, [cancelPrefetch]);

  const prefetchRun = useCallback(
    (runId) => {
      cancelPrefetch();
      if (!selectedProject || !runId) return;
      timerRef.current = setTimeout(() => {
        timerRef.current = null;
        // Historical runs are immutable (see useDashboard), so a cached entry
        // is good until a mutation invalidates it — and prefetchQuery refetches
        // invalidated entries regardless of staleTime.
        const staleTime = runId !== "latest" ? Infinity : STALE_TIME_MS;
        // Dashboard payload (the main render).
        queryClient.prefetchQuery({
          queryKey: projectKeys.dashboard(selectedProject, runId, selectedSource),
          queryFn: () => fetchDashboard(selectedProject, runId),
          staleTime,
        });
        // Scores payload (drives accumulated + trend).
        const asOf = runId !== "latest" ? runId : null;
        queryClient.prefetchQuery({
          queryKey: projectKeys.scores(selectedProject, asOf, selectedSource),
          queryFn: () => fetchScores(selectedProject, asOf),
          staleTime,
        });
      }, PREFETCH_DWELL_MS);
    },
    [queryClient, fetchDashboard, fetchScores, selectedProject, selectedSource, cancelPrefetch],
  );

  return { prefetchRun, cancelPrefetch };
}
