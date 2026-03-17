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
export function scoreColorClass(score) {
  const n = parseFloat(score);
  if (isNaN(n)) return 'grade-none';
  if (n >= 9) return 'grade-top';    // exemplary
  if (n >= 7) return 'grade-high';   // good
  if (n >= 5) return 'grade-mid';    // adequate
  if (n >= 3) return 'grade-low';    // poor
  return 'grade-bottom';             // critical
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
 * Format a date string as "20 Feb" (day + abbreviated month, no year).
 * Falls back to the original string if it cannot be parsed as a date.
 *
 * @param {string|null|undefined} dateStr
 * @returns {string}
 */
export function formatShortDate(dateStr) {
  if (!dateStr) return dateStr;
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
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

export function angleFromDelta(d) {
  const clamped = Math.max(-4, Math.min(4, d));
  return 90 - Math.sign(clamped) * Math.sqrt(Math.abs(clamped) / 4) * 55;
}

export function scoreTierLabel(score) {
  const n = parseFloat(score);
  if (isNaN(n)) return '';
  if (n >= 9) return 'A';
  if (n >= 7) return 'B';
  if (n >= 5) return 'C';
  if (n >= 3) return 'D';
  return 'F';
}

const GRADE_LABEL_MAP = { exemplary: 'A', good: 'B', proficient: 'B', adequate: 'C', developing: 'C', poor: 'D', insufficient: 'D', critical: 'F' };

export function gradeLabel(grade) {
  if (!grade) return null;
  const k = grade.trim().toLowerCase();
  if (GRADE_LABEL_MAP[k]) return GRADE_LABEL_MAP[k];
  const firstChar = grade.trim().toUpperCase().charAt(0);
  return ['A', 'B', 'C', 'D', 'F'].includes(firstChar) ? firstChar : null;
}

export function complianceRatio(violations, compliance) {
  if (violations === 0) return '\u2014';
  return `1:${Math.round(compliance / violations)}`;
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
