import { mostFrequentGrade } from '../../utils/formatters.js';

/**
 * Build an aggregate run summary from dimension data.
 *
 * Prefers the pre-computed `summary` from the API when available.
 * Falls back to client-side aggregation when the API response does
 * not include it (legacy endpoints or partial responses).
 *
 * Once the API always returns a summary, the fallback below can be removed.
 */
export default function buildRunSummary(dimensions, apiSummary) {
  if (apiSummary) return apiSummary;
  if (!dimensions || dimensions.length === 0) {
    return {
      overallGrade: '-',
      numericAverage: null,
      totalViolations: 0,
      totalCompliance: 0,
      dimensionCount: 0,
      severity: { critical: 0, major: 0, minor: 0 },
      dismissed: 0,
    };
  }

  const grades = dimensions.map((d) => d.overallGrade).filter(Boolean);
  const scores = dimensions.map((d) => parseFloat(d.overallScore)).filter((s) => !isNaN(s));
  const numericAverage =
    scores.length > 0
      ? (scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(1)
      : null;

  let totalViolations = 0, totalCompliance = 0, critical = 0, major = 0, minor = 0, dismissed = 0;
  for (const d of dimensions) {
    totalViolations += d.totals?.violationCount || 0;
    totalCompliance += d.totals?.complianceCount || 0;
    critical += d.totals?.severity?.critical || 0;
    major += d.totals?.severity?.major || 0;
    minor += d.totals?.severity?.minor || 0;
    dismissed += typeof d.dismissedCount === 'number' ? d.dismissedCount : 0;
  }

  return {
    overallGrade: mostFrequentGrade(grades) || '-',
    numericAverage,
    totalViolations,
    totalCompliance,
    dimensionCount: dimensions.length,
    severity: { critical, major, minor },
    dismissed,
  };
}
