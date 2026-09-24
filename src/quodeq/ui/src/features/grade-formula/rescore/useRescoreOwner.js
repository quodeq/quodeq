import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getGradeFormula } from '../../../api/index.js';
import { gradeFormulaKeys, projectKeys } from '../../../api/queryKeys.js';
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
    console.warn('[useRescoreOwner] progress poll failed:', err);
    return queryClient.getQueryData(gradeFormulaKeys.rescore()) ?? null;
  }
}

/**
 * The poll behind RescoreTrackerProvider. track(payload) follows the pass a
 * 202 (or a mount GET that shows a running pass) describes. When it settles,
 * the whole `project` query subtree is dropped: the pass rewrote the grade
 * tables of every run, and completed-run dashboard queries never go stale
 * on their own (see useDashboard.js). Then every subscribe()d listener gets
 * the settling payload, for page-local follow-up (notices, preview refresh).
 * @returns {{rescore: object|undefined, target: number|null, track: Function, subscribe: Function}}
 */
export function useRescoreOwner() {
  const queryClient = useQueryClient();
  const [target, setTarget] = useState(null);
  const listenersRef = useRef(new Set());

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
    // Fire-and-forget by design (see useRunEventStream.js): a poll GET
    // already in flight for the PREVIOUS target must not land after this
    // setQueryData and overwrite it with a stale generation -- isRescoreSettled
    // would then read `generation < target` as a server restart and settle
    // at once. Still log a rejection instead of letting it vanish silently.
    queryClient.cancelQueries({ queryKey: gradeFormulaKeys.rescore() }).catch((err) => {
      console.warn('[useRescoreOwner] cancelQueries failed:', err);
    });
    queryClient.setQueryData(gradeFormulaKeys.rescore(), payload);
    setTarget(payload.rescore.generation);
  }, [queryClient]);

  const subscribe = useCallback((listener) => {
    listenersRef.current.add(listener);
    return () => listenersRef.current.delete(listener);
  }, []);

  const rescore = data?.rescore;
  useEffect(() => {
    if (target === null || !isRescoreSettled(rescore, target)) return;
    setTarget(null);
    queryClient.invalidateQueries({ queryKey: projectKeys.all() });
    listenersRef.current.forEach((listener) => listener(data));
  }, [data, rescore, target, queryClient]);

  return useMemo(() => ({ rescore, target, track, subscribe }), [rescore, target, track, subscribe]);
}
