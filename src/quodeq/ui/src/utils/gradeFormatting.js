import { getGradeThresholds } from './gradeThresholds.js';

/**
 * Format a numeric score (0-10) to one decimal place, or the placeholder
 * dash when it doesn't parse to a number.
 *
 * @param {number|string|null|undefined} score
 * @returns {string}
 */
export function formatScoreDisplay(score) {
  const n = typeof score === 'number' ? score : parseFloat(score);
  return Number.isNaN(n) ? '—' : n.toFixed(1);
}

/**
 * Grade-to-CSS-class mapping.
 * Full word keys take priority; single-letter keys serve as fallback.
 */
export const GRADE_TIERS = {
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
  if (!score) return { value: '—', denom: '' };
  const m = String(score).match(/^(\d+(?:\.\d+)?)(\/10)/);
  return m ? { value: m[1], denom: m[2] } : { value: score, denom: '' };
}

const GRADE_CLASSES = ['grade-top', 'grade-high', 'grade-mid', 'grade-low'];
const TIER_LETTERS = ['A', 'B', 'C', 'D'];
const BOTTOM_TIER_LETTER = 'F';
const ALL_TIER_LETTERS = [...TIER_LETTERS, BOTTOM_TIER_LETTER];

// Walk the served grade bands highest-first and label the first one the score
// reaches. `labels` is positional (index 0 = highest band); `extraBand` covers
// a served threshold list longer than `labels`, `bottom` a score below every
// band and `notANumber` a score that does not parse. scoreColorClass and
// scoreTierLabel are the same walk with different labels.
function scoreBandLabel(score, { labels, extraBand, bottom, notANumber }) {
  const n = typeof score === 'number' ? score : parseFloat(score);
  if (Number.isNaN(n)) return notANumber;
  const thresholds = getGradeThresholds();
  for (let i = 0; i < thresholds.length; i += 1) {
    if (n >= thresholds[i][0]) return labels[i] ?? extraBand;
  }
  return bottom;
}

/**
 * Map a numeric score (0–10) to a CSS grade class.
 *
 * Boundaries come from the served grade thresholds (gradeThresholds.js) so the
 * class buckets stay in lock-step with the active grade formula. The class
 * names are positional: index 0 (highest band) → grade-top, then high/mid/low.
 *
 * @param {number|string|null|undefined} score
 * @returns {string}
 */
export function scoreColorClass(score) {
  return scoreBandLabel(score, {
    labels: GRADE_CLASSES,
    extraBand: 'grade-low',
    bottom: 'grade-bottom',
    notANumber: 'grade-none',
  });
}

export const GRADE_WORD_TO_LETTER = {
  exemplary: 'A', good: 'B', proficient: 'B', adequate: 'C',
  developing: 'C', poor: 'D', insufficient: 'D', critical: 'F',
};

/**
 * Convert a grade word like "Good" to its letter ("B").
 * If already a letter or short string, returns as-is.
 */
export function gradeLetter(grade) {
  if (!grade) return '—';
  const lower = grade.trim().toLowerCase();
  return GRADE_WORD_TO_LETTER[lower] || grade;
}

const GRADE_COLOR_VARS = {
  'grade-top':    'var(--color-grade-top-text)',
  'grade-high':   'var(--color-grade-high-text)',
  'grade-mid':    'var(--color-grade-mid-text)',
  'grade-low':    'var(--color-grade-low-text)',
  'grade-bottom': 'var(--color-grade-bottom-text)',
  'grade-none':   'var(--color-text-muted)',
};

/**
 * Map a numeric score to its CSS custom property string for the grade color.
 * @param {number|string} score
 * @returns {string} e.g. 'var(--color-grade-high-text)'
 */
export function scoreGradeColorVar(score) {
  return GRADE_COLOR_VARS[scoreColorClass(score)] || 'var(--color-text-muted)';
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
 * Map a numeric score (0-10) to a letter tier label (A-F).
 *
 * @param {number|string} score - Numeric score value
 * @returns {string} Single letter grade ('A', 'B', 'C', 'D', 'F') or empty string
 */
export function scoreTierLabel(score) {
  return scoreBandLabel(score, {
    labels: TIER_LETTERS,
    extraBand: TIER_LETTERS[TIER_LETTERS.length - 1],
    bottom: BOTTOM_TIER_LETTER,
    notANumber: '',
  });
}

/**
 * Convert a word grade (e.g. "exemplary", "good") to a single letter label.
 * Falls back to the first character if it is a known letter grade.
 */
export function gradeLabel(grade) {
  if (!grade) return null;
  const k = grade.trim().toLowerCase();
  if (GRADE_WORD_TO_LETTER[k]) return GRADE_WORD_TO_LETTER[k];
  const firstChar = grade.trim().toUpperCase().charAt(0);
  return ALL_TIER_LETTERS.includes(firstChar) ? firstChar : null;
}

/**
 * Find the most frequently occurring grade in a list and return it capitalized.
 *
 * @param {string[]} grades - Array of grade strings
 * @returns {string|null} The most common grade (capitalized) or null if empty
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
