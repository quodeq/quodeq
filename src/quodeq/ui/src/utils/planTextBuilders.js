import { buildGroupPlanText } from './planBuilder.js';
import { SEVERITY_ORDER } from './formatters.js';

const addEntryTitle = (v) => ({ ...v, _entryTitle: v.principle || 'Violation' });

/**
 * Build a copy-friendly plan text summarising violations for a single file.
 * @param {{ file: string, violationsBySeverity: Object }} file - File object with violation data.
 * @param {string} [severityFilter] - Optional severity to filter by ('all', 'critical', 'major', 'minor', 'compliance').
 * @returns {string} Formatted plan text.
 */
export function buildFilePlanText(file, severityFilter) {
  if (severityFilter === 'compliance') {
    return '_No violations match the current filter._';
  }
  const allViolations = [];
  const violationsBySeverity = {};
  for (const sev of SEVERITY_ORDER) {
    if (severityFilter && severityFilter !== 'all' && severityFilter !== sev) {
      violationsBySeverity[sev] = [];
      continue;
    }
    const mapped = (file.violationsBySeverity?.[sev] || []).map(addEntryTitle);
    violationsBySeverity[sev] = mapped;
    allViolations.push(...mapped);
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
export function buildPrinciplePlanText(principle, violations, violationsBySeverity, principleData, severityFilter) {
  if (violations !== undefined) {
    if (severityFilter === 'compliance') {
      return '_No violations match the current filter._';
    }
    let filteredViolations = violations;
    let filteredBySeverity = violationsBySeverity;
    if (severityFilter && severityFilter !== 'all') {
      filteredViolations = (violations || []).filter(
        (v) => (v.severity || 'minor').toLowerCase() === severityFilter,
      );
      filteredBySeverity = {};
      for (const sev of SEVERITY_ORDER) {
        filteredBySeverity[sev] = sev === severityFilter ? (violationsBySeverity?.[sev] || []) : [];
      }
    }
    return buildGroupPlanText({
      title: principle,
      violations: filteredViolations,
      violationsBySeverity: filteredBySeverity,
      context: principleData?.findings || undefined,
    });
  }
  const allViolations = principle.violations || [];
  const bySeverity = {};
  for (const sev of SEVERITY_ORDER) {
    bySeverity[sev] = allViolations.filter((v) => (v.severity || 'minor').toLowerCase() === sev);
  }
  return buildGroupPlanText({ title: principle.principle, violations: allViolations, violationsBySeverity: bySeverity });
}
