import { mostFrequentGrade } from '../../utils/formatters.js';
import { emptySeverityCounts, sumSeverityTallies } from '../../utils/severity.js';

/** The shape buildRunSummary returns for a run with no dimension data. */
function emptySummary() {
  return {
    overallGrade: '-',
    numericAverage: null,
    totalViolations: 0,
    totalCompliance: 0,
    dimensionCount: 0,
    severity: emptySeverityCounts(),
    dismissed: 0,
    suppressed: 0,
  };
}

/** Mean of the parsed scores to one decimal, or null when none parsed. */
function averageScore(scores) {
  if (scores.length === 0) return null;
  return (scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(1);
}

/** Running totals across every dimension: counts and triage. */
function sumDimensionTotals(dimensions) {
  const sums = {
    totalViolations: 0, totalCompliance: 0,
    dismissed: 0, suppressed: 0,
  };
  for (const d of dimensions) {
    sums.totalViolations += d.totals?.violationCount || 0;
    sums.totalCompliance += d.totals?.complianceCount || 0;
    sums.dismissed += typeof d.dismissedCount === 'number' ? d.dismissedCount : 0;
    // Dismissed AND deleted. On a project with a triage history this dwarfs
    // `dismissed` -- deletions suppress a whole principle across a file and
    // accumulate across runs, while the scan re-finds them every time.
    sums.suppressed += typeof d.suppressedCount === 'number' ? d.suppressedCount : 0;
  }
  return sums;
}

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
  if (!dimensions || dimensions.length === 0) return emptySummary();

  const grades = dimensions.map((d) => d.overallGrade).filter(Boolean);
  const scores = dimensions.map((d) => parseFloat(d.overallScore)).filter((s) => !isNaN(s));
  const { totalViolations, totalCompliance, dismissed, suppressed } = sumDimensionTotals(dimensions);

  return {
    overallGrade: mostFrequentGrade(grades) || '-',
    numericAverage: averageScore(scores),
    totalViolations,
    totalCompliance,
    dimensionCount: dimensions.length,
    severity: sumSeverityTallies(dimensions.map((d) => d.totals || {})),
    dismissed,
    suppressed,
  };
}
