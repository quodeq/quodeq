import { countBySeverity } from './severity.js';

/**
 * Roll a dimensions array up into the counts the page headers show. Callers
 * pass the ALREADY filtered list, so hiding a standard changes the totals.
 *
 * @param {Array<{violations: Array, compliance: Array}>} dimensions
 * @returns {{totalViolations: number, totalCompliance: number, severity: Object}}
 *   `severity` carries one key per bucket severity.js defines, always present
 *   and zeroed, so callers never have to guard a missing severity.
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
