import { buildGroupPlanText } from './planBuilder.js';
import { KNOWN_SEVERITIES } from './constants.js';
import { SEVERITY, SEVERITY_FILTER_ALL } from '../vocab/severity.js';
import { FINDING_TYPE } from '../vocab/findingType.js';

const addEntryTitle = (v) => ({ ...v, _entryTitle: v.principle || 'Violation' });

/**
 * Build a copy-friendly plan text summarising violations for a single file.
 * @param {{ file: string, violationsBySeverity: Object }} file - File object with violation data.
 * @param {string} [severityFilter] - Optional severity to filter by ('all', 'critical', 'major', 'minor', 'compliance').
 * @returns {string} Formatted plan text.
 */
export function buildFilePlanText(file, severityFilter) {
  if (severityFilter === FINDING_TYPE.COMPLIANCE) {
    return '_No violations match the current filter._';
  }
  const allViolations = [];
  const violationsBySeverity = {};
  for (const sev of KNOWN_SEVERITIES) {
    if (severityFilter && severityFilter !== SEVERITY_FILTER_ALL && severityFilter !== sev) {
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
 * @param {Object} args
 * @param {string} args.principle - Principle name, used as the plan title.
 * @param {Array} args.violations - Flat array of violation objects.
 * @param {Object} args.violationsBySeverity - The same violations keyed by severity.
 * @param {Object} [args.principleData] - Extra principle data; `.findings` becomes the plan context.
 * @param {string} [args.severityFilter] - null/'all' (no filter), 'critical'/'major'/'minor'
 *   (only that bucket), or 'compliance' (returns `_No violations match the current filter._`).
 * @returns {string} Formatted plan text.
 */
export function buildPrinciplePlanText({ principle, violations, violationsBySeverity, principleData, severityFilter }) {
  if (severityFilter === FINDING_TYPE.COMPLIANCE) {
    return '_No violations match the current filter._';
  }
  let filteredViolations = violations;
  let filteredBySeverity = violationsBySeverity;
  if (severityFilter && severityFilter !== SEVERITY_FILTER_ALL) {
    filteredViolations = (violations || []).filter(
      (v) => (v.severity || SEVERITY.MINOR).toLowerCase() === severityFilter,
    );
    filteredBySeverity = {};
    for (const sev of KNOWN_SEVERITIES) {
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
