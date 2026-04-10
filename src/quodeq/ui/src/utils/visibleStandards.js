import { VISIBLE_STANDARDS_STORAGE_KEY, DEFAULT_VISIBLE_STANDARDS } from '../constants.js';

/**
 * Read the visible standard IDs from localStorage.
 * Returns the default ISO dimensions if nothing is stored.
 */
export function readVisibleStandardIds() {
  try {
    const raw = localStorage.getItem(VISIBLE_STANDARDS_STORAGE_KEY);
    if (!raw) return DEFAULT_VISIBLE_STANDARDS;
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : DEFAULT_VISIBLE_STANDARDS;
  } catch {
    return DEFAULT_VISIBLE_STANDARDS;
  }
}

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
    for (const v of violations) {
      const s = (v.severity || '').toLowerCase();
      if (s === 'critical') severity.critical++;
      else if (s === 'major') severity.major++;
      else if (s === 'minor') severity.minor++;
    }
  }
  return { totalViolations, totalCompliance, severity };
}
