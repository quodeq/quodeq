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
import { usePrefetchRun } from "./usePrefetchRun.js";

export function usePrefetchAdjacentRuns({ selectedProject, selectedSource = "local", availableRuns, overviewRunIndex }) {
  const { prefetchRun } = usePrefetchRun(selectedProject, selectedSource);

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
