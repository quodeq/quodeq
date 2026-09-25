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

const UNKNOWN_SEVERITY = 'unknown'; // fallback bucket for a severity value KNOWN_SEVERITIES doesn't recognise

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
  const counts = emptySeverityCounts();
  for (const v of violations || []) {
    counts[summaryBucket(v?.severity)]++;
  }
  return counts;
}

/**
 * A zeroed three-bucket tally. Each call returns a new object, so callers
 * may mutate it.
 *
 * @returns {{critical: number, major: number, minor: number}}
 */
export function emptySeverityCounts() {
  return { critical: 0, major: 0, minor: 0 };
}

/**
 * Adds up the `severity` tallies of a list of items (rows, standings), a
 * missing tally or bucket counting as zero.
 *
 * @param {Array<{severity?: {critical?: number, major?: number, minor?: number}|null}>} items
 * @returns {{critical: number, major: number, minor: number}}
 */
export function sumSeverityTallies(items) {
  return items.reduce(
    (acc, item) => ({
      critical: acc.critical + (item.severity?.critical || 0),
      major: acc.major + (item.severity?.major || 0),
      minor: acc.minor + (item.severity?.minor || 0),
    }),
    emptySeverityCounts(),
  );
}
