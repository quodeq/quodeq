// The jittered delay lands in [JITTER_FLOOR, 1] x the capped delay.
const JITTER_FLOOR = 0.5;
const JITTER_SPAN = 1 - JITTER_FLOOR;

/**
 * Jittered exponential backoff delay, in milliseconds, for a retry attempt.
 * `attempt` is 0 for the first retry. The result is capped at `maxMs` and
 * then jittered to half-to-full of that value, so concurrent retriers (e.g.
 * multiple tabs reconnecting after a shared server restart) don't all fire
 * on the same tick.
 *
 * @param {number} attempt - 0-based retry attempt count.
 * @param {number} baseMs - delay for the first attempt, before jitter.
 * @param {number} maxMs - upper bound on the delay, before jitter.
 * @returns {number}
 */
export function backoffDelay(attempt, baseMs, maxMs) {
  return Math.min(baseMs * 2 ** attempt, maxMs) * (JITTER_FLOOR + Math.random() * JITTER_SPAN);
}
