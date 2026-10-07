import { useEffect, useRef, useState } from 'react';

/**
 * Return true while *value* is true, and keep returning true until *minMs*
 * have passed since mount, then follow *value*. Used to keep the startup
 * loader up long enough to read a tip: a warm boot releases its data-hold
 * in a fraction of a second, and a loader that flashes for one frame reads
 * as a glitch rather than a loading screen.
 * One-way like useLinger: starting false never holds, and once the hold
 * has dropped it never re-arms.
 */
export function useMinimumHold(value, minMs) {
  const [elapsed, setElapsed] = useState(false);
  const startedRef = useRef(value);
  useEffect(() => {
    if (!startedRef.current) return undefined;
    const id = setTimeout(() => setElapsed(true), minMs);
    return () => clearTimeout(id);
  }, [minMs]);
  return startedRef.current && (value || !elapsed);
}
