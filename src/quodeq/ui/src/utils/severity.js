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

// Fallback bucket for a severity value KNOWN_SEVERITIES doesn't recognise.
const UNKNOWN_SEVERITY = 'unknown';

/**
 * Coerces any severity value to one of the four known ones, mapping anything
 * unrecognised (including null) to 'unknown'.
 *
 * @returns {'critical'|'major'|'minor'|'unknown'}
 */
export function normalizeSeverity(value) {
  const normalized = String(value || UNKNOWN_SEVERITY).toLowerCase();
  return KNOWN_SEVERITIES.includes(normalized) ? normalized : UNKNOWN_SEVERITY;
}

/**
 * Like normalizeSeverity, but folds 'unknown' into 'minor' so the three
 * summary chips always add up to the violation total.
 *
 * @returns {'critical'|'major'|'minor'}
 */
export function summaryBucket(value) {
  const normalized = normalizeSeverity(value);
  return normalized === UNKNOWN_SEVERITY ? 'minor' : normalized;
}

/**
 * Counts violations into the three summary buckets. Every entry lands in
 * exactly one, so the counts sum to the list length.
 *
 * @returns {{critical: number, major: number, minor: number}}
 */
export function countBySeverity(violations) {
  const counts = { critical: 0, major: 0, minor: 0 };
  for (const v of violations || []) {
    counts[summaryBucket(v?.severity)]++;
  }
  return counts;
}
