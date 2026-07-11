/**
 * Shared helpers for dimension data used by dashboard overview panels.
 */

/**
 * Augment file objects with a comma-separated dimensions string.
 */
export function withDimensionsStr(files) {
  return files.map((f) => ({
    ...f,
    dimensionsStr: f.dimensions?.length > 0 ? f.dimensions.join(', ') : '',
  }));
}

/**
 * Run-based delta fallback for a dimension when no period-aware trend entry is
 * available (defensive; the accumulated overview always supplies dimTrends).
 * Returns overallScore - previousScore, or null when either is not numeric.
 */
export function fallbackDelta(dim) {
  const curr = parseFloat(dim.overallScore);
  const prev = parseFloat(dim.previousScore);
  return !Number.isNaN(curr) && !Number.isNaN(prev) ? curr - prev : null;
}

/**
 * Sort dimensions by violation severity (critical > major > minor),
 * keeping only dimensions that have at least one violation.
 */
export function sortDimensionsByViolationSeverity(dimensions) {
  return [...dimensions]
    .filter((d) => (d.violations || []).length > 0)
    .map((d) => {
      const counts = { critical: 0, major: 0, minor: 0 };
      (d.violations || []).forEach((v) => {
        const s = (v.severity || 'minor').toLowerCase();
        if (counts[s] !== undefined) counts[s]++;
      });
      return { ...d, _c: counts };
    })
    .sort((a, b) => {
      if (b._c.critical !== a._c.critical) return b._c.critical - a._c.critical;
      if (b._c.major !== a._c.major) return b._c.major - a._c.major;
      return b._c.minor - a._c.minor;
    });
}
