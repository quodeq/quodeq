import { useEffect, useRef, useState } from 'react';

/**
 * Return true while *value* is true, and keep returning true for *delayMs*
 * after it drops, then settle false. Used to hold the startup loader
 * opaque for a beat after its data-hold releases: the overview beneath
 * needs one more commit (the lazy chart's first render) before the fade
 * starts, or the fade reveals a placeholder inside otherwise-real content.
 * One-way by design: a value that flips back to true during the linger is
 * ignored (the caller gates re-arms separately, see useOneShotGate).
 */
export function useLinger(value, delayMs) {
  const [lingering, setLingering] = useState(value);
  const startedRef = useRef(value);
  useEffect(() => {
    if (!startedRef.current || value) return undefined;
    const id = setTimeout(() => setLingering(false), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);
  return startedRef.current && (value || lingering);
}
