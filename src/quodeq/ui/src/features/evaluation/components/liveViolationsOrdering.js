/**
 * Ordering for LiveViolationsFeed: dimensions by most-recently-active first,
 * severity within a dimension.
 */
import { SEVERITY } from '../../../vocab/severity.js';

function severityOrder(s) {
  return s === SEVERITY.CRITICAL ? 0 : s === SEVERITY.MAJOR ? 1 : 2;
}

export const sameDim = (a, b) => Boolean(a) && Boolean(b) && String(a).toLowerCase() === String(b).toLowerCase();

/** A copy of one dimension's findings, worst first. */
export function sortBySeverity(violations) {
  return [...(violations ?? [])].sort((a, b) => severityOrder(a.severity) - severityOrder(b.severity));
}

/**
 * The dimensions that have findings, in display order. Each keeps its own
 * list as is: sorting thousands of rows on every arrival is wasted work for
 * a group that is closed, so the open group sorts its own (sortBySeverity).
 *
 * @param {Record<string, Array>} liveViolations
 * @param {Record<string, number>} lastActivity
 * @param {string|null|undefined} [currentDimension] the dimension being
 *   analyzed, kept on top: the activity clock restarts on every mount, so
 *   after a tab switch every dimension ties and only this says which is live.
 */
export function orderDimensions(liveViolations, lastActivity, currentDimension = null) {
  const liveFirst = (d) => (sameDim(d.dim, currentDimension) ? 0 : 1);
  return Object.entries(liveViolations ?? {})
    .map(([dim, vs]) => ({ dim, violations: vs ?? [] }))
    .filter(({ violations }) => violations.length > 0)
    .sort((a, b) => liveFirst(a) - liveFirst(b) || (lastActivity[b.dim] ?? 0) - (lastActivity[a.dim] ?? 0));
}
