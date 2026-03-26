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
 * Map a numeric score (0–10) to a CSS grade class.
 *
 * @param {number|string|null|undefined} score
 * @returns {string}
 */
const SCORE_EXEMPLARY = 9;
const SCORE_GOOD = 7;
const SCORE_ADEQUATE = 5;
const SCORE_POOR = 3;

export function scoreColorClass(score) {
  const n = parseFloat(score);
  if (isNaN(n)) return 'grade-none';
  if (n >= SCORE_EXEMPLARY) return 'grade-top';
  if (n >= SCORE_GOOD) return 'grade-high';
  if (n >= SCORE_ADEQUATE) return 'grade-mid';
  if (n >= SCORE_POOR) return 'grade-low';
  return 'grade-bottom';
}

const GRADE_WORD_TO_LETTER = {
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

const EXT_DISPLAY_NAMES = {
  py: 'Python', js: 'JavaScript', ts: 'TypeScript', jsx: 'JSX', tsx: 'TSX',
  sh: 'Shell', bash: 'Shell', rb: 'Ruby', go: 'Go', rs: 'Rust',
  java: 'Java', kt: 'Kotlin', cs: 'C#', swift: 'Swift', dart: 'Dart',
  css: 'CSS', html: 'HTML', vue: 'Vue', php: 'PHP', c: 'C', cpp: 'C++',
};

/** Map a file extension to a human-readable language name. */
export function extDisplayName(ext) {
  return EXT_DISPLAY_NAMES[ext.toLowerCase()] || ext;
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
 * Format a date string as "20 Feb 2026" (day + abbreviated month + year).
 * Falls back to the original string if it cannot be parsed as a date.
 *
 * @param {string|null|undefined} dateStr
 * @returns {string}
 */
export function formatShortDate(dateStr) {
  if (!dateStr) return dateStr;
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
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
export const SEVERITY_ORDER = ['critical', 'major', 'minor', 'unknown'];

export function parseFileRef(rawFile, rawLine) {
  if (!rawFile) return { filePath: null, line: rawLine ?? null };
  const m = rawFile.match(/^(.*?)(?::(\d+))?$/);
  const filePath = m[1] || rawFile;
  const line = rawLine ?? (m[2] ? parseInt(m[2], 10) : null);
  return { filePath, line };
}

/**
 * Convert a score delta into a rotation angle for trend arrows.
 * Clamps the delta to [-4, 4] and maps it to an angle around 90 degrees.
 *
 * @param {number} d - Score delta value
 * @returns {number} Rotation angle in degrees (35..145)
 */
const DELTA_CLAMP = 4;
const ANGLE_BASE = 90;
const ANGLE_RANGE = 55;

export function angleFromDelta(d) {
  const clamped = Math.max(-DELTA_CLAMP, Math.min(DELTA_CLAMP, d));
  return ANGLE_BASE - Math.sign(clamped) * Math.sqrt(Math.abs(clamped) / DELTA_CLAMP) * ANGLE_RANGE;
}

/**
 * Map a numeric score (0-10) to a letter tier label (A-F).
 *
 * @param {number|string} score - Numeric score value
 * @returns {string} Single letter grade ('A', 'B', 'C', 'D', 'F') or empty string
 */
export function scoreTierLabel(score) {
  const n = parseFloat(score);
  if (isNaN(n)) return '';
  if (n >= SCORE_EXEMPLARY) return 'A';
  if (n >= SCORE_GOOD) return 'B';
  if (n >= SCORE_ADEQUATE) return 'C';
  if (n >= SCORE_POOR) return 'D';
  return 'F';
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
  return ['A', 'B', 'C', 'D', 'F'].includes(firstChar) ? firstChar : null;
}

/**
 * Format the ratio of compliance items to violations as a readable string.
 *
 * @param {number} violations - Number of violations
 * @param {number} compliance - Number of compliance items
 * @returns {string} Formatted ratio string (e.g. "1:5") or em-dash when no violations
 */
export function complianceRatio(violations, compliance) {
  if (violations === 0) return '\u2014';
  return `1:${Math.round(compliance / violations)}`;
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
