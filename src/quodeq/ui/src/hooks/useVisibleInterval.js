import { useEffect, useRef } from 'react';
import { isHidden, subscribeVisibility } from '../utils/appVisibility.js';

/**
 * setInterval that only runs while the app window is visible, and fires once
 * on return so the user does not wait a full period for fresh data.
 *
 * `ms` falsy means no timer at all, which is how callers express "this poll
 * is not active right now" without an extra effect. `callback` is read from a
 * ref, so a caller that rebuilds it every render does not restart the clock.
 *
 * @param {() => void} callback
 * @param {number|false|null} ms
 */
export function useVisibleInterval(callback, ms) {
  const latest = useRef(callback);
  latest.current = callback;

  useEffect(() => {
    if (!ms) return undefined;
    let id = null;
    const tick = () => latest.current();
    const stop = () => {
      if (id === null) return;
      clearInterval(id);
      id = null;
    };
    const sync = (catchUp) => {
      if (isHidden()) {
        stop();
        return;
      }
      if (id !== null) return;
      if (catchUp) tick();
      id = setInterval(tick, ms);
    };
    sync(false);
    const unsubscribe = subscribeVisibility(() => sync(true));
    return () => { stop(); unsubscribe(); };
  }, [ms]);
}
