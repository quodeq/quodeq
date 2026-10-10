import { useCallback, useEffect, useRef, useState } from 'react';
import { rescoreGradeFormula } from '../../api/index.js';
import { useRescoreTracker } from '../grade-formula/rescore/RescoreTrackerContext.js';
import { useWarmupSnapshot } from './warmupSnapshot.js';
import { REBUILD_STATE, isBusyState, pickRebuildState } from './rebuildState.js';

// How long the done row stays after the work ends, long enough to read.
export const DONE_LINGER_MS = 3000;

/**
 * True for DONE_LINGER_MS after `busy` drops, every time it drops (unlike
 * useLinger, which is one-shot: a rebuild can run several times a session).
 */
function useDoneBeat(busy, ms) {
  const [done, setDone] = useState(false);
  const wasBusy = useRef(false);
  useEffect(() => {
    if (busy) {
      wasBusy.current = true;
      setDone(false);
      return undefined;
    }
    if (!wasBusy.current) return undefined;
    wasBusy.current = false;
    setDone(true);
    const id = setTimeout(() => setDone(false), ms);
    return () => clearTimeout(id);
  }, [busy, ms]);
  return done;
}

/**
 * What the rebuild strip shows, from the app-level rescore tracker and the
 * warm-up snapshot the project list records. `finished` is the last busy
 * state, so the done row can say what finished. `retry` runs the formula
 * pass again after a failure and hands the 202 to the tracker, which then
 * follows it like a pass started from Settings.
 * @returns {{state: Object, finished: Object|null, retry: Function, retrying: boolean}}
 */
export function useRebuildStatus() {
  const { rescore, target, track } = useRescoreTracker();
  const warmup = useWarmupSnapshot();
  const picked = pickRebuildState({ rescore, tracking: target !== null, warmup });
  const busy = isBusyState(picked.kind);
  const finishedRef = useRef(null);
  if (busy) finishedRef.current = { kind: picked.kind, total: picked.total };
  const doneBeat = useDoneBeat(busy, DONE_LINGER_MS);
  const [retrying, setRetrying] = useState(false);

  const retry = useCallback(() => {
    setRetrying(true);
    rescoreGradeFormula()
      .then((payload) => { track(payload); })
      .catch((err) => { console.warn('[useRebuildStatus] retry failed:', err); })
      .finally(() => setRetrying(false));
  }, [track]);

  const state = busy || picked.kind === REBUILD_STATE.FAILED
    ? picked
    : (doneBeat ? { kind: REBUILD_STATE.DONE, done: 0, total: 0 } : picked);
  return { state, finished: finishedRef.current, retry, retrying };
}
