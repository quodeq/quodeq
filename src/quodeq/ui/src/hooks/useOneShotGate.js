import { useRef } from 'react';

/**
 * Pass `active` through until the first render where it is false, then
 * return false forever. Used to scope the startup loader to boot: the hold
 * predicate describes a *state* ("overview data not in yet"), and a
 * mid-session project switch re-enters that state — without the gate the
 * fullscreen loader would flash over the app on every switch (e.g. opening
 * a project from Compare). Ref-latched during render on purpose: the latch
 * must be consumed in the same render that drops the value, or a
 * same-batch re-entry could re-arm it before an effect ran.
 */
export function useOneShotGate(active) {
  const consumedRef = useRef(false);
  if (consumedRef.current) return false;
  if (!active) {
    consumedRef.current = true;
    return false;
  }
  return true;
}
