import { buildTopOffendingFiles } from '../../utils/explorerUtils.js';
import { withDimensionsStr } from '../../utils/dimensionUtils.js';
import buildRunSummary from './buildRunSummary.js';
import { buildHeadline, sumSinceBaseline } from './headlineStats.js';

const dimKey = (name) => (name || '').toLowerCase();

/**
 * The dashboard's dimensions (overview shape: scores and counts) with each
 * one's finding lists taken from the run findings (api `/scores/<run>`).
 * A dimension without findings loaded keeps no list, so readers that test
 * `Array.isArray(violations)` wait instead of seeing zero findings.
 * @param {Array} dashboardDims
 * @param {Array} findingDims
 * @returns {Array}
 */
export function withRunFindings(dashboardDims, findingDims) {
  const byName = new Map((findingDims || []).map((d) => [dimKey(d.dimension), d]));
  if (byName.size === 0) return dashboardDims || [];
  return (dashboardDims || []).map((dim) => {
    const found = byName.get(dimKey(dim.dimension));
    if (!found) return dim;
    const merged = { ...dim };
    if (Array.isArray(found.violations)) merged.violations = found.violations;
    if (Array.isArray(found.compliance)) merged.compliance = found.compliance;
    return merged;
  });
}

/**
 * Everything the run overview derives from the dashboard payload and the
 * run's findings: the summary, the since-baseline totals, the worst files,
 * the headline and the merged `dimensions` the report and fix plan print.
 * Pure, so the panel memoizes one call on the two identities.
 * @param {Object} dashboard Overview-shape dashboard payload.
 * @param {Array} [findingDims] The run findings' dimensions, [] while loading.
 */
export function buildRunViewData(dashboard, findingDims = []) {
  const dimensions = withRunFindings(dashboard?.dimensions, findingDims);
  return {
    dimensions,
    runSummary: buildRunSummary(dashboard?.dimensions),
    since: sumSinceBaseline(dashboard?.sinceBaseline),
    runTopFiles: withDimensionsStr(buildTopOffendingFiles(dimensions)),
    headline: buildHeadline(dashboard?.dimensions),
  };
}
