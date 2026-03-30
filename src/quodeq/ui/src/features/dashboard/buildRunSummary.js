import { mostFrequentGrade } from '../../utils/formatters.js';

/**
 * Build an aggregate run summary from dimension data already received
 * from the API.  This duplicates some backend logic but avoids an extra
 * round-trip — the API does not always provide a pre-computed summary.
 */
export default function buildRunSummary(dimensions) {
  if (!dimensions || dimensions.length === 0) {
    return {
      overallGrade: '-',
      numericAverage: null,
      totalViolations: 0,
      totalCompliance: 0,
      dimensionCount: 0,
      severity: { critical: 0, major: 0, minor: 0 },
    };
  }

  const grades = dimensions.map((d) => d.overallGrade).filter(Boolean);
  const scores = dimensions.map((d) => parseFloat(d.overallScore)).filter((s) => !isNaN(s));
  const numericAverage =
    scores.length > 0
      ? (scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(1)
      : null;

  return {
    overallGrade: mostFrequentGrade(grades) || '-',
    numericAverage,
    totalViolations: dimensions.reduce((sum, d) => sum + (d.totals?.violationCount || 0), 0),
    totalCompliance: dimensions.reduce((sum, d) => sum + (d.totals?.complianceCount || 0), 0),
    dimensionCount: dimensions.length,
    severity: {
      critical: dimensions.reduce((sum, d) => sum + (d.totals?.severity?.critical || 0), 0),
      major: dimensions.reduce((sum, d) => sum + (d.totals?.severity?.major || 0), 0),
      minor: dimensions.reduce((sum, d) => sum + (d.totals?.severity?.minor || 0), 0),
    },
  };
}
