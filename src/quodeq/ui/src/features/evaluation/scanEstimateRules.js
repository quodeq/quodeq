/**
 * Pure rules over the pre-run per-dimension file estimates (`/projects/:id/estimates`).
 * Extracted out of RunBar (ReEvaluateCardParts.jsx) verbatim.
 */

/**
 * Total file analyses the currently-picked dimensions will queue, given the
 * per-dimension estimates. `null` when there is nothing to sum (no estimates,
 * or every picked dimension is missing from them) so the caller can fall back
 * to "duration depends on repo size" instead of showing a 0.
 *
 * @param {Set<string>} selectedDims
 * @param {{ dimensions?: Object<string, { total?: number, count?: number }> }|null} estimates
 * @param {boolean} isClean - clean/full rescan vs incremental
 * @returns {number|null}
 */
export function queuedFileAnalyses(selectedDims, estimates, isClean) {
  if (!estimates?.dimensions) return null;
  return [...selectedDims].reduce((sum, id) => {
    const est = estimates.dimensions[id];
    if (!est) return sum;
    return (sum ?? 0) + (isClean ? (est.total ?? 0) : (est.count ?? 0));
  }, null);
}
