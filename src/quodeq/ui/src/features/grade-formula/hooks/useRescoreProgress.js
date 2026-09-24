import { useEffect, useRef } from 'react';
import { RESCORE_STATE } from '../../../vocab/rescoreState.js';
import { useRescoreTracker } from '../rescore/RescoreTrackerContext.js';

/**
 * The Grade Formula page's view of the app-level rescore tracker
 * (rescore/RescoreTrackerProvider.jsx). The tracker owns the poll and the
 * score-cache invalidation, so both survive the page unmounting; this hook
 * only reads progress for display and hears about the settle while mounted.
 * @param {Function} onSettled - receives the settling GET payload, once per pass.
 * @param {object|null} resumeFrom - a mount GET payload whose pass is still
 *   running (the user came back mid-pass); tracked like a fresh 202.
 * @returns {{rescoreProgress: {done: number, total: number}|null, track: Function}}
 *   track(payload) starts following the pass a 202 payload describes.
 */
export function useRescoreProgress(onSettled, resumeFrom) {
  const { rescore, target, track, subscribe } = useRescoreTracker();
  const onSettledRef = useRef(onSettled);
  onSettledRef.current = onSettled;

  useEffect(() => subscribe((payload) => onSettledRef.current(payload)), [subscribe]);

  useEffect(() => {
    if (resumeFrom) track(resumeFrom);
  }, [resumeFrom, track]);

  const running = target !== null && rescore?.state === RESCORE_STATE.RUNNING;
  return { rescoreProgress: running ? { done: rescore.done, total: rescore.total } : null, track };
}
