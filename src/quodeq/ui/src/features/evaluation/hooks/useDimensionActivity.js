/**
 * Track the most recent activity timestamp per dimension so we can sort
 * "latest active first". The ref persists across renders; we update it
 * whenever a dim's violation count changes.
 *
 * Split out of LiveViolationsFeed.jsx verbatim.
 */
import { useRef } from 'react';

export function useDimensionActivity(liveViolations) {
  const lastActivityRef = useRef({});
  const prevCountsRef = useRef({});
  const now = Date.now();
  for (const [dim, vs] of Object.entries(liveViolations || {})) {
    const len = (vs || []).length;
    if (prevCountsRef.current[dim] !== len) {
      prevCountsRef.current[dim] = len;
      lastActivityRef.current[dim] = now;
    }
  }
  return lastActivityRef.current;
}
