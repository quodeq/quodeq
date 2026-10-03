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

const sameDim = (a, b) => Boolean(a) && Boolean(b) && String(a).toLowerCase() === String(b).toLowerCase();

/**
 * @param {Record<string, Array>} liveViolations
 * @param {Record<string, number>} lastActivity
 * @param {string|null|undefined} [currentDimension] the dimension being
 *   analyzed, kept on top: the activity clock restarts on every mount, so
 *   after a tab switch every dimension ties and only this says which is live.
 */
export function orderDimensions(liveViolations, lastActivity, currentDimension = null) {
  const liveFirst = (d) => (sameDim(d.dim, currentDimension) ? 0 : 1);
  return Object.entries(liveViolations ?? {})
    .map(([dim, vs]) => ({
      dim,
      violations: [...(vs ?? [])].sort((a, b) => severityOrder(a.severity) - severityOrder(b.severity)),
    }))
    .filter(({ violations }) => violations.length > 0)
    .sort((a, b) => liveFirst(a) - liveFirst(b) || (lastActivity[b.dim] ?? 0) - (lastActivity[a.dim] ?? 0));
}

/**
 * The group the accordion holds open. While the run is on, the dimension
 * being analyzed: its group when it has findings, none while it has none yet.
 * Once the run is over (or when the progress names no dimension), the top
 * group. Before the progress has loaded there is no answer, so the caller
 * leaves the accordion alone rather than opening the wrong group for a beat.
 * @param {{isRunning: boolean, progress: Object|undefined, orderedDims: Array<{dim: string}>}} args
 * @returns {string|null|undefined} the dim to open, null for none, undefined for no answer yet
 */
export function autoOpenTarget({ isRunning, progress, orderedDims }) {
  const top = orderedDims[0]?.dim ?? null;
  if (!isRunning) return top;
  if (!progress) return undefined;
  const current = progress.currentDimension;
  if (!current) return top;
  return orderedDims.find((d) => sameDim(d.dim, current))?.dim ?? null;
}
