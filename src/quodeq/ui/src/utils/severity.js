/**
 * Single source of truth for severity handling.
 *
 * Two vocabularies exist on purpose:
 * - Display/filtering uses the full set (critical/major/minor/unknown):
 *   normalizeSeverity.
 * - Summary counters (the chips next to a total) use three buckets, with
 *   unknown folded into minor so critical+major+minor always equals the
 *   violation total: summaryBucket / countBySeverity. Before this module
 *   seven independent implementations disagreed on the fold and chip sums
 *   drifted from totals whenever a finding lacked a severity.
 */
import { KNOWN_SEVERITIES } from './constants.js';

export function normalizeSeverity(value) {
  const normalized = String(value || 'unknown').toLowerCase();
  return KNOWN_SEVERITIES.includes(normalized) ? normalized : 'unknown';
}

export function summaryBucket(value) {
  const normalized = normalizeSeverity(value);
  return normalized === 'unknown' ? 'minor' : normalized;
}

export function countBySeverity(violations) {
  const counts = { critical: 0, major: 0, minor: 0 };
  for (const v of violations || []) {
    counts[summaryBucket(v?.severity)]++;
  }
  return counts;
}
