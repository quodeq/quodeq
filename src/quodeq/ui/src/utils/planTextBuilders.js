import { buildGroupPlanText } from './planBuilder.js';
import { SEVERITY_ORDER } from './formatters.js';

const addEntryTitle = (v) => ({ ...v, _entryTitle: v.principle || 'Violation' });

/**
 * Build a copy-friendly plan text summarising violations for a single file.
 * @param {{ file: string, violationsBySeverity: Object }} file - File object with violation data.
 * @returns {string} Formatted plan text.
 */
export function buildFilePlanText(file) {
  const allViolations = SEVERITY_ORDER.flatMap((sev) =>
    (file.violationsBySeverity?.[sev] || []).map(addEntryTitle)
  );
  const violationsBySeverity = {};
  for (const sev of SEVERITY_ORDER) {
    violationsBySeverity[sev] = (file.violationsBySeverity?.[sev] || []).map(addEntryTitle);
  }
  return buildGroupPlanText({
    title: `\`${file.file}\``,
    violations: allViolations,
    violationsBySeverity,
  });
}

/**
 * Build plan text for a principle's violations.
 *
 * Supports two calling conventions:
 * 1. Pre-split data: `buildPrinciplePlanText(principleName, violations, violationsBySeverity, principleData)`
 *    where `principle` is a string name and violations/violationsBySeverity are provided explicitly.
 * 2. Principle object: `buildPrinciplePlanText(principleObj)` where `principleObj` has `.principle`,
 *    `.violations`, etc. — violations are derived automatically.
 *
 * @param {string|Object} principle - Principle name (string) or principle object with `.principle` and `.violations`.
 * @param {Array} [violations] - Flat array of violation objects (convention 1 only).
 * @param {Object} [violationsBySeverity] - Violations keyed by severity (convention 1 only).
 * @param {Object} [principleData] - Optional extra data (e.g. `.findings`) for convention 1.
 * @returns {string} Formatted plan text.
 */
export function buildPrinciplePlanText(principle, violations, violationsBySeverity, principleData) {
  if (violations !== undefined) {
    return buildGroupPlanText({ title: principle, violations, violationsBySeverity, context: principleData?.findings || undefined });
  }
  const allViolations = principle.violations || [];
  const bySeverity = {};
  for (const sev of SEVERITY_ORDER) {
    bySeverity[sev] = allViolations.filter((v) => (v.severity || 'minor').toLowerCase() === sev);
  }
  return buildGroupPlanText({ title: principle.principle, violations: allViolations, violationsBySeverity: bySeverity });
}
