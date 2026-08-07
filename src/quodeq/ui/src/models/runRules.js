/**
 * Domain rules about runs and findings.
 *
 * These are decisions about the domain, not about rendering: whether a run's
 * data can still change, whether a finding is worth de-emphasising, which
 * grading tier a score falls into. They lived inside a data-fetching hook and
 * two components, which made them invisible to anyone reading the domain and
 * untestable without React. Same shape as `exitReason.js`: pure functions,
 * no framework imports.
 */

/**
 * Confidence below which a finding is grouped away as low-signal.
 * Matches the backend's own reporting threshold.
 */
export const LOW_CONFIDENCE_THRESHOLD = 50;

/** Score tiers, mirroring the backend grading bands (see core scoring params). */
export const SCORE_THRESHOLDS = { exemplary: 9, good: 7, adequate: 5, poor: 3 };

/**
 * True when the selected run's data can no longer change.
 *
 * A frozen run may be cached indefinitely; a live one must keep refetching.
 * Three rules, each load-bearing:
 *  - no selection is not frozen;
 *  - "latest" is never frozen — it points at a moving target;
 *  - an UNKNOWN run counts as frozen. By the time a run detail is opened the
 *    runs list is already cached, so treating the brief unknown window as
 *    frozen avoids a spurious refetch on mount.
 */
export function isFrozenRun(selectedRun, availableRuns) {
  if (!selectedRun || selectedRun === 'latest') return false;
  const status = (availableRuns || []).find((r) => r.runId === selectedRun)?.status;
  return status !== 'in_progress';
}

/** True when a finding's confidence is below the low-signal threshold. */
export function isLowConfidence(finding) {
  return typeof finding?.confidence === 'number'
    && finding.confidence < LOW_CONFIDENCE_THRESHOLD;
}

/**
 * The grading tier for a numeric score, or null when there is no score.
 * Null is distinct from 'unacceptable': "not scored" is not a bad grade.
 */
export function scoreTier(score) {
  if (typeof score !== 'number' || Number.isNaN(score)) return null;
  if (score >= SCORE_THRESHOLDS.exemplary) return 'exemplary';
  if (score >= SCORE_THRESHOLDS.good) return 'good';
  if (score >= SCORE_THRESHOLDS.adequate) return 'adequate';
  if (score >= SCORE_THRESHOLDS.poor) return 'poor';
  return 'unacceptable';
}
