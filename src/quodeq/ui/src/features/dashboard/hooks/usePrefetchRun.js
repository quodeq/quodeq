/**
 * Prefetch a single run's dashboard + scores payloads into the query cache.
 *
 * Pairs with the run-detail views: warming the cache on hover means that by
 * the time the user clicks, the data is often already there and the loading
 * state is skipped entirely. Shared by the overview run navigator
 * (usePrefetchAdjacentRuns) and the History table rows.
 */
import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useApi } from "../../../api/ApiContext.jsx";
import { getProjectScores } from "../../../api/index.js";
import { projectKeys } from "../../../api/queryKeys.js";

const STALE_TIME_MS = 60_000;

export function usePrefetchRun(selectedProject) {
  const queryClient = useQueryClient();
  const { getDashboard } = useApi();

  return useCallback(
    (runId) => {
      if (!selectedProject || !runId) return;
      // Historical runs are immutable (see useDashboard), so a cached entry
      // is good until a mutation invalidates it — and prefetchQuery refetches
      // invalidated entries regardless of staleTime.
      const staleTime = runId !== "latest" ? Infinity : STALE_TIME_MS;
      // Dashboard payload (the main render).
      queryClient.prefetchQuery({
        queryKey: projectKeys.dashboard(selectedProject, runId),
        queryFn: () => getDashboard(selectedProject, runId),
        staleTime,
      });
      // Scores payload (drives accumulated + trend).
      const asOf = runId !== "latest" ? runId : null;
      queryClient.prefetchQuery({
        queryKey: projectKeys.scores(selectedProject, asOf),
        queryFn: () => getProjectScores(selectedProject, asOf),
        staleTime,
      });
    },
    [queryClient, getDashboard, selectedProject],
  );
}
