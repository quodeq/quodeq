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
import { DEFAULT_PROJECT_SOURCE } from "../../../constants.js";

/**
 * Mouse-enter handlers for the run navigator that warm the adjacent runs'
 * caches, so Prev/Next/Latest usually swap with no visible load.
 *
 * @returns {{onPrevHover: Function, onNextHover: Function, onLatestHover: Function}}
 */
export function usePrefetchAdjacentRuns({ selectedProject, selectedSource = DEFAULT_PROJECT_SOURCE, availableRuns, overviewRunIndex }) {
  const { prefetchRun } = usePrefetchRun(selectedProject, selectedSource);

  // Warm the run at `idx`, if there is one there. An index past either end of
  // the list just means nothing to prefetch.
  const prefetchAt = useCallback((idx) => {
    const runId = availableRuns[idx]?.runId;
    if (runId) prefetchRun(runId);
  }, [availableRuns, prefetchRun]);

  const onPrevHover = useCallback(() => {
    prefetchAt(Math.min(overviewRunIndex + 1, availableRuns.length - 1));
  }, [overviewRunIndex, availableRuns, prefetchAt]);

  const onNextHover = useCallback(() => {
    prefetchAt(Math.max(overviewRunIndex - 1, 0));
  }, [overviewRunIndex, prefetchAt]);

  const onLatestHover = useCallback(() => {
    prefetchAt(0);
  }, [prefetchAt]);

  return { onPrevHover, onNextHover, onLatestHover };
}
