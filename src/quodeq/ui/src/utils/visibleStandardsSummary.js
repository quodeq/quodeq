import { countBySeverity } from './severity.js';

/**
 * Compute summary stats from a filtered dimensions array.
 */
export function computeSummaryFromDimensions(dimensions) {
  let totalViolations = 0;
  let totalCompliance = 0;
  const severity = { critical: 0, major: 0, minor: 0 };
  for (const d of dimensions) {
    const violations = d.violations || [];
    totalViolations += violations.length;
    totalCompliance += d.compliance?.length || 0;
    const counts = countBySeverity(violations);
    severity.critical += counts.critical;
    severity.major += counts.major;
    severity.minor += counts.minor;
  }
  return { totalViolations, totalCompliance, severity };
}
