import { useCallback, useRef, useState } from 'react';

// Coalescing wrapper around a single async refresh round (`refreshCore`):
// a call that arrives while one is already running doesn't start a second
// round immediately -- it marks the run as pending and is satisfied by
// exactly one more round once the current one settles, no matter how many
// calls stack up in the meantime (audit C3 groundwork; the old in-flight
// guard used to just silently ignore the repeat call, which is how a
// post-publish refresh could get dropped on the floor).
//
// runningRef marks a round actually in flight; pendingRef marks that at
// least one more caller arrived while it was running and must be satisfied
// by an EXTRA round once the current one settles; waitersRef holds those
// callers' resolvers so their returned promise only settles once the round
// they asked for has actually run. Extracted verbatim from
// useSharedProjects.js.
export function useCoalescedRefresh(refreshCore) {
  const [refreshing, setRefreshing] = useState(false);
  const runningRef = useRef(false);
  const pendingRef = useRef(false);
  const waitersRef = useRef([]);

  const refresh = useCallback(() => {
    if (runningRef.current) {
      pendingRef.current = true;
      return new Promise((resolve) => { waitersRef.current.push(resolve); });
    }
    runningRef.current = true;
    setRefreshing(true);
    return (async () => {
      try {
        await refreshCore();
        // Coalesce: run exactly one more round for every batch of callers
        // that arrived while the previous round was in flight, instead of
        // one round per call.
        while (pendingRef.current) {
          pendingRef.current = false;
          const waiters = waitersRef.current;
          waitersRef.current = [];
          await refreshCore();
          waiters.forEach((resolve) => resolve());
        }
      } finally {
        runningRef.current = false;
        setRefreshing(false);
      }
    })();
  }, [refreshCore]);

  return { refreshing, refresh };
}
