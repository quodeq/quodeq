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
