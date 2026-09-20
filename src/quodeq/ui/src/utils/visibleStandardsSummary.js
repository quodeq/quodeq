import { countBySeverity } from './severity.js';

/**
 * Compute summary stats from a filtered dimensions array.
 */
export function computeSummaryFromDimensions(dimensions) {
  let totalViolations = 0;
  let totalCompliance = 0;
  // Zeroed via countBySeverity's own bucket shape instead of re-listing the
  // severity names here, so a new bucket only needs adding in severity.js.
  const severity = countBySeverity([]);
  for (const d of dimensions) {
    const violations = d.violations || [];
    totalViolations += violations.length;
    totalCompliance += d.compliance?.length || 0;
    const counts = countBySeverity(violations);
    for (const key of Object.keys(severity)) severity[key] += counts[key];
  }
  return { totalViolations, totalCompliance, severity };
}
