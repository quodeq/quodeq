/**
 * Grade-to-CSS-class mapping.
 * Full word keys take priority; single-letter keys serve as fallback.
 */
const GRADE_TIERS = {
  exemplary:    'grade-top',
  good:         'grade-high',
  proficient:   'grade-high',
  adequate:     'grade-mid',
  developing:   'grade-mid',
  poor:         'grade-low',
  insufficient: 'grade-low',
  critical:     'grade-bottom',
  // Letter grades
  a: 'grade-top',
  b: 'grade-high',
  c: 'grade-mid',
  d: 'grade-low',
  f: 'grade-bottom',
};

/**
 * Split a score string such as "7.5/10 Good" or "8/10" into its
 * numeric part and denominator.
 *
 * @param {string|null|undefined} score
 * @returns {{ value: string, denom: string }}
 */
export function splitScore(score) {
  if (!score) return { value: '\u2014', denom: '' };
  const m = String(score).match(/^(\d+(?:\.\d+)?)(\/10)/);
  return m ? { value: m[1], denom: m[2] } : { value: score, denom: '' };
}

/**
 * Map a grade word or letter to a CSS class.
 * Tries the full lower-cased word first, then the first character.
 *
 * @param {string|null|undefined} grade
 * @returns {string}
 */
export function gradeColorClass(grade) {
  if (!grade) return 'grade-none';
  const lower = grade.trim().toLowerCase();
  if (GRADE_TIERS[lower]) return GRADE_TIERS[lower];
  const first = lower.charAt(0);
  return GRADE_TIERS[first] || 'grade-none';
}

/**
 * Format a run identifier for display.
 * - If a dateLabel is provided, use it directly.
 * - "latest" (or falsy) becomes "Latest".
 * - Otherwise return a truncated UUID as fallback.
 *
 * @param {string|null|undefined} runId
 * @param {string|null|undefined} dateLabel
 * @returns {string}
 */
export function formatRunId(runId, dateLabel) {
  if (dateLabel) return dateLabel;
  if (!runId || runId === 'latest') return 'Latest';
  // Truncate UUID for compact display
  const s = String(runId);
  return s.length > 8 ? s.slice(0, 8) + '…' : s;
}

/**
 * Capitalize the first letter of a grade string and lowercase the rest.
 *
 * @param {string|null|undefined} str
 * @returns {string|null|undefined}
 */
export function capitalizeGrade(str) {
  if (!str) return str;
  return str.charAt(0).toUpperCase() + str.slice(1).toLowerCase();
}

/**
 * Return the most frequently occurring grade in the array.
 * Ties are broken by first encountered order.
 * Grade strings are normalized to lowercase before counting.
 *
 * @param {string[]} grades
 * @returns {string|null}
 */
/**
 * Strip leading "Principle — " or "Principle - " prefix from reason text
 * to avoid duplication when the principle is shown separately.
 */
export function stripPrinciplePrefix(reason, principle) {
  if (!reason || !principle) return reason;
  for (const sep of [' \u2014 ', ' — ', ' - ']) {
    if (reason.startsWith(principle + sep)) {
      return reason.slice(principle.length + sep.length);
    }
  }
  return reason;
}
export function mostFrequentGrade(grades) {
  if (!grades || grades.length === 0) return null;
  const counts = {};
  grades.forEach((g) => {
    const normalized = (g || '').trim().toLowerCase();
    if (normalized) counts[normalized] = (counts[normalized] || 0) + 1;
  });
  let maxGrade = null;
  let maxCount = 0;
  Object.entries(counts).forEach(([grade, count]) => {
    if (count > maxCount) {
      maxCount = count;
      maxGrade = grade;
    }
  });
  return capitalizeGrade(maxGrade);
}
