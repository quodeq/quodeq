/** Shared trend-direction thresholds used by TrendBadge and HistoryChartPanel. */
export const IMPROVING_THRESHOLD = 1;
export const DECLINING_THRESHOLD = -1;
export const SOFT_UP_THRESHOLD = 0.1;
export const SOFT_DOWN_THRESHOLD = -0.1;

/**
 * Compute a trend direction string from a numeric delta.
 * @param {number|null|undefined} delta
 * @returns {'up'|'soft-up'|'same'|'soft-down'|'down'|null}
 */
export function trendDirection(delta) {
  if (delta === null || delta === undefined) return null;
  if (delta > IMPROVING_THRESHOLD) return 'up';
  if (delta > SOFT_UP_THRESHOLD) return 'soft-up';
  if (delta < DECLINING_THRESHOLD) return 'down';
  if (delta < SOFT_DOWN_THRESHOLD) return 'soft-down';
  return 'same';
}
