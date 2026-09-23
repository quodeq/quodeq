/**
 * Ordering for LiveViolationsFeed: severity within a dimension, dimensions
 * by most-recently-active first.
 *
 * Split out of LiveViolationsFeed.jsx verbatim.
 */
import { SEVERITY } from '../../../vocab/severity.js';

function severityOrder(s) {
  return s === SEVERITY.CRITICAL ? 0 : s === SEVERITY.MAJOR ? 1 : 2;
}

export function orderDimensions(liveViolations, lastActivity) {
  return Object.entries(liveViolations ?? {})
    .map(([dim, vs]) => ({
      dim,
      violations: [...(vs ?? [])].sort((a, b) => severityOrder(a.severity) - severityOrder(b.severity)),
    }))
    .filter(({ violations }) => violations.length > 0)
    .sort((a, b) => (lastActivity[b.dim] ?? 0) - (lastActivity[a.dim] ?? 0));
}
