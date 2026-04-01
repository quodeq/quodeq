import { buildGroupPlanText } from './planBuilder.js';
import { SEVERITY_ORDER } from './formatters.js';

export function buildFilePlanText(file) {
  const allViolations = SEVERITY_ORDER.flatMap((sev) =>
    (file.violationsBySeverity?.[sev] || []).map((v) => ({ ...v, _entryTitle: v.principle || 'Violation' }))
  );
  const violationsBySeverity = {};
  for (const sev of SEVERITY_ORDER) {
    violationsBySeverity[sev] = (file.violationsBySeverity?.[sev] || []).map((v) => ({ ...v, _entryTitle: v.principle || 'Violation' }));
  }
  return buildGroupPlanText({
    title: `\`${file.file}\``,
    violations: allViolations,
    violationsBySeverity,
  });
}

export function buildPrinciplePlanText(principle, violations, violationsBySeverity, principleData) {
  // When violations are provided directly, use them; otherwise derive from principle object.
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
