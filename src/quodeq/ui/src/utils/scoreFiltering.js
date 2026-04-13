/**
 * Pure functions for filtering scores by visible standards.
 *
 * No side effects, no API calls. These operate on the pre-rescored data
 * returned by the unified /scores endpoint.
 */

const roundOneDecimal = (n) => Math.round(n * 10) / 10;

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
    for (const d of (entry.dimensionDetails || [])) {
      const dimId = (d.dimension || '').toLowerCase();
      if (visibleSet.has(dimId) && d.score != null) {
        accByDim[dimId] = d.score;
      }
    }
    const accScores = Object.values(accByDim).filter((s) => s != null);
    const accAvg = accScores.length > 0 ? roundOneDecimal(accScores.reduce((a, b) => a + b, 0) / accScores.length) : null;
    accByRun.set(entry.runId, accAvg);
  }
  return trend
    .map((entry) => {
      const accAvg = accByRun.get(entry.runId) ?? null;
      const visibleDetails = (entry.dimensionDetails || []).filter((d) => visibleSet.has((d.dimension || '').toLowerCase()));
      const runScores = visibleDetails.map((d) => d.score).filter((s) => s != null);
      const runAvg = runScores.length > 0 ? roundOneDecimal(runScores.reduce((a, b) => a + b, 0) / runScores.length) : null;
      const dims = (entry.dimensions || []).filter((d) => visibleSet.has(d.toLowerCase()));
      return { ...entry, numericAverage: accAvg, runNumericAverage: runAvg, dimensionDetails: visibleDetails, dimensions: dims, dimensionsCount: dims.length };
    })
    .filter((entry) => entry.dimensionDetails.length > 0);
}

/**
 * Filter trend and collapse to daily entries (one per calendar day).
 *
 * Walks the raw trend oldest-first to build accumulated averages,
 * then maps onto dailyTrend entries (collapsed by day) for display.
 * Used by the Overview panel where bars represent days, not individual runs.
 *
 * @param {Array} trend - Raw trend entries (newest-first)
 * @param {Array} dailyTrend - Daily-collapsed trend entries (from collapseByDay)
 * @param {Set<string>} visibleSet - Lowercase dimension IDs to include
 * @returns {Array} Filtered daily trend entries (newest-first)
 */
export function filterTrendByVisibleStandardsDaily(trend, dailyTrend, visibleSet) {
  const accByDim = {};
  const accByDate = new Map(); // date string -> accAvg
  const visibleDates = new Set();
  const rawReversed = [...trend].reverse(); // oldest first
  for (const entry of rawReversed) {
    let hasVisible = false;
    for (const d of (entry.dimensionDetails || [])) {
      const dimId = (d.dimension || '').toLowerCase();
      if (visibleSet.has(dimId) && d.score != null) {
        accByDim[dimId] = d.score;
        hasVisible = true;
      }
    }
    if (hasVisible) {
      const accScores = Object.values(accByDim).filter((s) => s != null);
      const accAvg = accScores.length > 0 ? roundOneDecimal(accScores.reduce((a, b) => a + b, 0) / accScores.length) : null;
      const datePart = (entry.dateISO || '').slice(0, 10);
      accByDate.set(datePart, accAvg);
      visibleDates.add(datePart);
    }
  }
  // Match daily entries by date, only include days with visible evaluations
  return dailyTrend
    .filter((entry) => visibleDates.has((entry.dateISO || '').slice(0, 10)))
    .map((entry) => {
      const datePart = (entry.dateISO || '').slice(0, 10);
      const accAvg = accByDate.get(datePart) ?? null;
      const details = (entry.dimensionDetails || []).filter((d) => visibleSet.has((d.dimension || '').toLowerCase()));
      const runScores = details.map((d) => d.score).filter((s) => s != null);
      const runAvg = runScores.length > 0 ? roundOneDecimal(runScores.reduce((a, b) => a + b, 0) / runScores.length) : null;
      const dims = (entry.dimensions || []).filter((d) => visibleSet.has(d.toLowerCase()));
      return { ...entry, numericAverage: accAvg, runNumericAverage: runAvg, dimensionDetails: details, dimensions: dims, dimensionsCount: dims.length };
    });
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

  // Use the trend's accumulated average (consistent with History)
  const selectedIdx = selectedRunId ? filteredTrend.findIndex((t) => t.runId === selectedRunId) : 0;
  const idx = selectedIdx >= 0 ? selectedIdx : 0;
  const trendAvg = idx < filteredTrend.length ? parseFloat(filteredTrend[idx]?.numericAverage) : null;
  const numericAverage = (trendAvg != null && !isNaN(trendAvg)) ? trendAvg : null;
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
      severity.minor += sev.minor || 0;
    } else {
      const violations = d.violations || [];
      totalViolations += violations.length;
      totalCompliance += d.compliance?.length || 0;
      for (const v of violations) {
        const s = (v.severity || '').toLowerCase();
        if (s === 'critical') severity.critical++;
        else if (s === 'major') severity.major++;
        else if (s === 'minor') severity.minor++;
      }
    }
  }
  return { totalViolations, totalCompliance, severity };
}
