/**
 * Pure functions for filtering scores by visible standards.
 *
 * No side effects, no API calls. These operate on the pre-rescored data
 * returned by the unified /scores endpoint.
 */

import { bucketKey, isBucketEligible } from './dailyGrouping.js';
import { scoreToGradeLabel } from './gradeThresholds.js';
import { countBySeverity } from './severity.js';

const roundOneDecimal = (n) => Math.round(n * 10) / 10;

// Mean of the scores that are present, rounded to one decimal. null when
// nothing is left after dropping the missing ones.
function meanScore(scores) {
  const present = scores.filter((s) => s != null);
  if (present.length === 0) return null;
  return roundOneDecimal(present.reduce((a, b) => a + b, 0) / present.length);
}

// The entry's dimensionDetails narrowed to the visible set.
function visibleDetailsOf(entry, visibleSet) {
  return (entry.dimensionDetails || []).filter((d) => visibleSet.has((d.dimension || '').toLowerCase()));
}

// Record each visible dimension score on `accByDim` as that dimension's
// latest known value. Returns whether this entry contributed any.
function foldVisibleScores(accByDim, entry, visibleSet) {
  let hasVisible = false;
  for (const d of (entry.dimensionDetails || [])) {
    const dimId = (d.dimension || '').toLowerCase();
    if (visibleSet.has(dimId) && d.score != null) {
      accByDim[dimId] = d.score;
      hasVisible = true;
    }
  }
  return hasVisible;
}

// One entry projected onto the visible set: details and dimensions narrowed,
// run average recomputed from what is left, accumulated average as walked.
function projectEntry(entry, visibleSet, accAvg) {
  const details = visibleDetailsOf(entry, visibleSet);
  const dims = (entry.dimensions || []).filter((d) => visibleSet.has(d.toLowerCase()));
  return {
    ...entry,
    numericAverage: accAvg,
    runNumericAverage: meanScore(details.map((d) => d.score)),
    dimensionDetails: details,
    dimensions: dims,
    dimensionsCount: dims.length,
  };
}

/**
 * Filter trend entries to only include visible dimensions and recompute averages.
 *
 * Walks all runs oldest-first to build accumulated state at each point,
 * then maps each run with the accumulated average at that point in time.
 *
 * @param {Array} trend - Raw trend entries (newest-first)
 * @param {Set<string>} visibleSet - Lowercase dimension IDs to include
 * @returns {Array} Filtered trend entries (newest-first)
 */
export function filterTrendByVisibleStandards(trend, visibleSet) {
  const accByDim = {};
  const accByRun = new Map();
  const rawReversed = [...trend].reverse(); // oldest first
  for (const entry of rawReversed) {
    foldVisibleScores(accByDim, entry, visibleSet);
    accByRun.set(entry.runId, meanScore(Object.values(accByDim)));
  }
  return trend
    .map((entry) => projectEntry(entry, visibleSet, accByRun.get(entry.runId) ?? null))
    .filter((entry) => entry.dimensionDetails.length > 0);
}

/**
 * Filter trend and collapse to period entries (one per calendar day, week, or month).
 *
 * Walks the raw trend oldest-first to build accumulated averages,
 * then maps onto periodTrend entries (collapsed by the specified granularity) for display.
 * Used by the Overview panel where bars represent periods, not individual runs.
 *
 * @param {Array} trend - Raw trend entries (newest-first)
 * @param {Array} periodTrend - Period-collapsed trend entries (from collapseByPeriod)
 * @param {Set<string>} visibleSet - Lowercase dimension IDs to include
 * @param {'day'|'week'|'month'} [granularity='day'] - Bucket granularity
 * @returns {Array} Filtered period trend entries (newest-first)
 */
export function filterTrendByVisibleStandardsDaily(trend, periodTrend, visibleSet, granularity = 'day') {
  const accByDim = {};
  const accByKey = new Map(); // bucket key -> accAvg
  const visibleKeys = new Set();
  const rawReversed = [...trend].reverse(); // oldest first
  for (const entry of rawReversed) {
    // A running run's partial dims must not enter the bucket average: the
    // Overview header reads the selected bucket's numericAverage, and the
    // cards deliberately exclude in-progress runs — a partial score here
    // makes the headline disagree with the cards mid-scan.
    if (!isBucketEligible(entry)) continue;
    if (!foldVisibleScores(accByDim, entry, visibleSet)) continue;
    const key = bucketKey(entry.dateISO, granularity);
    accByKey.set(key, meanScore(Object.values(accByDim)));
    visibleKeys.add(key);
  }
  // Match period entries by bucket key, only include periods with visible evaluations
  return periodTrend
    .filter((entry) => visibleKeys.has(bucketKey(entry.dateISO, granularity)))
    .map((entry) => projectEntry(entry, visibleSet, accByKey.get(bucketKey(entry.dateISO, granularity)) ?? null));
}

/**
 * Filter accumulated dimensions by visible standards and recompute summary.
 *
 * @param {Object} accumulated - { dimensions, summary }
 * @param {Set<string>} visibleSet - Lowercase dimension IDs to include
 * @param {Array} filteredTrend - Already-filtered trend (for consistent averages)
 * @param {string|null} selectedRunId - Currently selected run
 * @returns {Object} Filtered accumulated with recomputed summary
 */
export function filterAccumulatedByVisibleStandards(accumulated, visibleSet, filteredTrend, selectedRunId) {
  if (!accumulated) return accumulated;
  const filteredDimensions = (accumulated.dimensions || []).filter((d) =>
    visibleSet.has((d.dimension || '').toLowerCase())
  );

  // Use the trend's accumulated average (consistent with History). When the
  // trend is empty — e.g. an all-cancelled project, whose runs aren't chart
  // points but whose kept-findings scores still populate the cards — fall
  // back to the accumulated summary so the header number agrees with the
  // dimension cards instead of reading "—" over visible scores.
  const selectedIdx = selectedRunId ? filteredTrend.findIndex((t) => t.runId === selectedRunId) : 0;
  const idx = selectedIdx >= 0 ? selectedIdx : 0;
  const trendAvg = idx < filteredTrend.length ? parseFloat(filteredTrend[idx]?.numericAverage) : null;
  const summaryAvg = parseFloat(accumulated.summary?.numericAverage);
  const numericAverage = (trendAvg != null && !isNaN(trendAvg))
    ? trendAvg
    : (!isNaN(summaryAvg) ? summaryAvg : null);
  const prevIdx = idx + 1;
  const prevAvg = prevIdx < filteredTrend.length ? parseFloat(filteredTrend[prevIdx]?.numericAverage) : null;

  const { totalViolations, totalCompliance, severity } = computeSummaryFromFilteredDimensions(filteredDimensions);

  return {
    ...accumulated,
    dimensions: filteredDimensions,
    summary: {
      ...accumulated.summary,
      numericAverage,
      previousNumericAverage: prevAvg,
      // Re-derive the grade word from the recomputed average: the backend's
      // overallGrade is computed over ALL dimensions, so passing it through
      // lets a hidden dimension's score set the letter next to a number it
      // no longer matches (score from visible dims, grade from everything).
      overallGrade: scoreToGradeLabel(numericAverage),
      totalViolations,
      totalCompliance,
      severity,
    },
  };
}

/**
 * Compute summary stats from a filtered dimensions array.
 * Handles both camelCase (API response) and array-based violations.
 *
 * @param {Array} dimensions
 * @returns {{ totalViolations: number, totalCompliance: number, severity: Object }}
 */
export function computeSummaryFromFilteredDimensions(dimensions) {
  let totalViolations = 0;
  let totalCompliance = 0;
  const severity = { critical: 0, major: 0, minor: 0 };
  for (const d of dimensions) {
    // Support both totals-based (from unified endpoint) and violations-array-based
    const totals = d.totals;
    if (totals) {
      totalViolations += totals.violationCount || 0;
      totalCompliance += totals.complianceCount || 0;
      const sev = totals.severity || {};
      severity.critical += sev.critical || 0;
      severity.major += sev.major || 0;
      // Fold the backend's 'unknown' bucket into minor so
      // critical+major+minor always equals violationCount.
      severity.minor += (sev.minor || 0) + (sev.unknown || 0);
    } else {
      const violations = d.violations || [];
      totalViolations += violations.length;
      totalCompliance += d.compliance?.length || 0;
      const counts = countBySeverity(violations);
      severity.critical += counts.critical;
      severity.major += counts.major;
      severity.minor += counts.minor;
    }
  }
  return { totalViolations, totalCompliance, severity };
}
