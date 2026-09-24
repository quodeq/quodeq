import { useCallback, useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getGradeFormula } from '../../../api/index.js';
import { gradeFormulaKeys } from '../../../api/queryKeys.js';
import { RESCORE_STATE } from '../../../vocab/rescoreState.js';

// One progress read per second while the server's background pass runs:
// often enough for "Rescoring N of M" to move, and the GET is a small JSON.
export const RESCORE_POLL_MS = 1000;

/**
 * True once the server is done with (or has given up on) the pass for
 * generation `target`:
 * - error: the pass raised; the server does not retry until the next apply.
 * - generation behind target: the server restarted and lost the job.
 * - not running and appliedGeneration caught up: the pass landed.
 */
export function isRescoreSettled(rescore, target) {
  if (!rescore) return false;
  if (rescore.state === RESCORE_STATE.ERROR) return true;
  if (rescore.generation < target) return true;
  return rescore.state !== RESCORE_STATE.RUNNING && rescore.appliedGeneration >= target;
}

async function readProgress(queryClient) {
  try {
    return await getGradeFormula();
  } catch (err) {
    // One failed poll (a restart, a dropped connection) must not end the
    // poll: keep the last known payload and try again next tick.
    console.warn('[useRescoreProgress] progress poll failed:', err);
    return queryClient.getQueryData(gradeFormulaKeys.rescore()) ?? null;
  }
}

/**
 * Poll GET /api/grade-formula after an apply/reset until its background
 * rescore settles, then call onSettled(payload) once.
 * @param {Function} onSettled - receives the settling GET payload.
 * @param {object|null} resumeFrom - a mount GET payload whose pass is still
 *   running (the user came back mid-pass); tracked like a fresh 202.
 * @returns {{rescoreProgress: {done: number, total: number}|null, track: Function}}
 *   track(payload) starts following the pass a 202 payload describes.
 */
export function useRescoreProgress(onSettled, resumeFrom) {
  const queryClient = useQueryClient();
  const [target, setTarget] = useState(null);
  const onSettledRef = useRef(onSettled);
  onSettledRef.current = onSettled;

  const { data } = useQuery({
    queryKey: gradeFormulaKeys.rescore(),
    queryFn: () => readProgress(queryClient),
    enabled: target !== null,
    refetchInterval: (query) => (isRescoreSettled(query.state.data?.rescore, target) ? false : RESCORE_POLL_MS),
    refetchOnWindowFocus: false,
    retry: false,
    staleTime: 0,
  });

  const track = useCallback((payload) => {
    queryClient.setQueryData(gradeFormulaKeys.rescore(), payload);
    setTarget(payload.rescore.generation);
  }, [queryClient]);

  useEffect(() => {
    if (resumeFrom) track(resumeFrom);
  }, [resumeFrom, track]);

  const rescore = data?.rescore;
  useEffect(() => {
    if (target === null || !isRescoreSettled(rescore, target)) return;
    setTarget(null);
    onSettledRef.current(data);
  }, [data, rescore, target]);

  const running = target !== null && rescore?.state === RESCORE_STATE.RUNNING;
  return { rescoreProgress: running ? { done: rescore.done, total: rescore.total } : null, track };
}
