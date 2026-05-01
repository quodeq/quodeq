/**
 * Prefetch the dashboard payload for adjacent runs on hover.
 *
 * Pairs with placeholderData in useDashboard / useProjectScores: by the time
 * the user clicks Prev / Next / Latest, the cache for that run is often
 * already warm, so the placeholder swap is invisible.
 *
 * Returns mouse-enter handlers to wire onto the run-navigator buttons.
 * The hook is no-op when the project or runs list is empty.
 */
import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useApi } from "../../../api/ApiContext.jsx";
import { getProjectScores } from "../../../api/index.js";
import { projectKeys } from "../../../api/queryKeys.js";

const STALE_TIME_MS = 60_000;

export function usePrefetchAdjacentRuns({ selectedProject, availableRuns, overviewRunIndex }) {
  const queryClient = useQueryClient();
  const { getDashboard } = useApi();

  const prefetchRun = useCallback(
    (runId) => {
      if (!selectedProject || !runId) return;
      // Dashboard payload (the main render).
      queryClient.prefetchQuery({
        queryKey: projectKeys.dashboard(selectedProject, runId),
        queryFn: () => getDashboard(selectedProject, runId),
        staleTime: STALE_TIME_MS,
      });
      // Scores payload (drives accumulated + trend).
      const asOf = runId !== "latest" ? runId : null;
      queryClient.prefetchQuery({
        queryKey: projectKeys.scores(selectedProject, asOf),
        queryFn: () => getProjectScores(selectedProject, asOf),
        staleTime: STALE_TIME_MS,
      });
    },
    [queryClient, getDashboard, selectedProject],
  );

  const onPrevHover = useCallback(() => {
    const idx = Math.min(overviewRunIndex + 1, availableRuns.length - 1);
    const runId = availableRuns[idx]?.runId;
    if (runId) prefetchRun(runId);
  }, [overviewRunIndex, availableRuns, prefetchRun]);

  const onNextHover = useCallback(() => {
    const idx = Math.max(overviewRunIndex - 1, 0);
    const runId = availableRuns[idx]?.runId;
    if (runId) prefetchRun(runId);
  }, [overviewRunIndex, availableRuns, prefetchRun]);

  const onLatestHover = useCallback(() => {
    const runId = availableRuns[0]?.runId;
    if (runId) prefetchRun(runId);
  }, [availableRuns, prefetchRun]);

  return { onPrevHover, onNextHover, onLatestHover };
}
