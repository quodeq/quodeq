/**
 * Strip leading "Principle — " or "Principle - " prefix from reason text
 * to avoid duplication when the principle is shown separately.
 */
export function stripPrinciplePrefix(reason, principle) {
  if (!reason || !principle) return reason;
  for (const sep of [' — ', ' — ', ' - ']) {
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
 * Format the ratio of compliance items to violations as a readable string.
 *
 * @param {number} violations - Number of violations
 * @param {number} compliance - Number of compliance items
 * @returns {string} Formatted ratio string (e.g. "1:5") or em-dash when no violations
 */
export function complianceRatio(violations, compliance) {
  if (violations === 0) return '—';
  return `1:${Math.round(compliance / violations)}`;
}
