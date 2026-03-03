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
 * - 8-digit strings are treated as YYYYMMDD and converted to "Mon DD YYYY".
 * - "latest" (or falsy) becomes "Latest".
 * - Everything else is returned unchanged.
 *
 * @param {string|null|undefined} runId
 * @returns {string}
 */
export function formatRunId(runId) {
  if (!runId || runId === 'latest') return 'Latest';
  const s = String(runId);
  if (s.length !== 8) return s;
  const year = s.slice(0, 4);
  const month = parseInt(s.slice(4, 6), 10);
  const day = parseInt(s.slice(6, 8), 10);
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const monthName = months[month - 1];
  if (!monthName) return s;
  return `${monthName} ${day}`;
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
