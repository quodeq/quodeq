/**
 * Single source of truth for severity handling.
 *
 * Two vocabularies exist on purpose:
 * - Display/filtering uses the full set (critical/major/minor/unknown):
 *   normalizeSeverity.
 * - Summary counters (the chips next to a total) use three buckets, with
 *   unknown folded into minor so critical+major+minor always equals the
 *   violation total: summaryBucket / countBySeverity. One implementation
 *   keeps chip sums equal to totals when a finding lacks a severity.
 * - Some views (explorer principle filtering, the galaxy viz, dimension
 *   utils) count raw severities instead: countKnownSeverities. It does not
 *   fold unknown into minor, so critical+major+minor can fall short of the
 *   violation total when a finding's severity isn't one of the three.
 */
import { KNOWN_SEVERITIES } from './constants.js';
import { SEVERITY } from '../vocab/severity.js';

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
 * Counts violations into the three buckets by their raw severity: a missing
 * severity counts as minor and any other value outside the three is not
 * counted. With `ignoreCase` each severity is lower-cased first.
 *
 * @param {Array<{severity?: string}>|null|undefined} violations
 * @param {{ignoreCase?: boolean}} [options]
 * @returns {{critical: number, major: number, minor: number}}
 */
export function countKnownSeverities(violations, { ignoreCase = false } = {}) {
  const counts = emptySeverityCounts();
  for (const v of violations || []) {
    const raw = v.severity || SEVERITY.MINOR;
    const sev = ignoreCase ? raw.toLowerCase() : raw;
    if (counts[sev] !== undefined) counts[sev]++;
  }
  return counts;
}

/**
 * One new empty list per display bucket (critical, major, minor, unknown).
 *
 * @returns {Record<'critical'|'major'|'minor'|'unknown', Array>}
 */
export function emptySeverityLists() {
  return Object.fromEntries(KNOWN_SEVERITIES.map((sev) => [sev, []]));
}

/**
 * The size of each display bucket's list.
 *
 * @param {Record<'critical'|'major'|'minor'|'unknown', Array>} lists
 * @returns {{critical: number, major: number, minor: number, unknown: number}}
 */
export function severityListCounts(lists) {
  return Object.fromEntries(KNOWN_SEVERITIES.map((sev) => [sev, lists[sev].length]));
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
