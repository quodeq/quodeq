/**
 * Ordering for LiveViolationsFeed: severity within a dimension, dimensions
 * by most-recently-active first.
 *
 * Split out of LiveViolationsFeed.jsx verbatim.
 */

function severityOrder(s) {
  return s === 'critical' ? 0 : s === 'major' ? 1 : 2;
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
