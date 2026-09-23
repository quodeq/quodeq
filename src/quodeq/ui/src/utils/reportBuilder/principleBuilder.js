// src/quodeq/ui/src/utils/reportBuilder/principleBuilder.js
import { formatDate, groupBySeverity, buildComplianceSection, buildViolationsSection, showsCompliance, runSuffix } from './shared.js';
import { SEVERITY } from '../../vocab/severity.js';

function buildPrincipleHeaderSection({ principle, dimension, score, grade, runId, dateLabel, principleData }) {
  const date = dateLabel || formatDate();
  const ridSuffix = runSuffix(runId);
  const dimSuffix = dimension ? ` · **Dimension:** ${dimension}` : '';
  const scoreDisplay = score ? `${String(score).replace('/10', '')}/10` : '—';

  const lines = [];
  lines.push(`# ${principle} report`);
  lines.push('');
  lines.push(`**Date:** ${date}${ridSuffix}${dimSuffix} · **Score:** ${scoreDisplay} ${grade || '—'}`);
  lines.push('');

  if (principleData?.findings) {
    lines.push('## Findings');
    lines.push('');
    lines.push(principleData.findings);
    lines.push('');
  }
  if (principleData?.justification) {
    lines.push('## Justification');
    lines.push('');
    lines.push(principleData.justification);
    lines.push('');
  }
  return lines;
}

/**
 * The full Markdown report for one principle. `severityFilter` narrows it to
 * what the user is currently looking at; 'compliance' drops the violations
 * section entirely.
 *
 * @returns {string}
 */
export function buildPrincipleReport({ principle, dimension, score, grade, violations, violationsBySeverity, compliance, principleData, runId, dateLabel, severityFilter }) {
  const rawViolations = violations || [];
  const complianceList = (compliance || []).filter((c) => c.file || c.reason || c.snippet);

  const lines = buildPrincipleHeaderSection({ principle, dimension, score, grade, runId, dateLabel, principleData });

  const showViolations = severityFilter !== 'compliance';
  const showCompliance = showsCompliance(severityFilter);

  const filteredViolations = (showViolations && severityFilter && severityFilter !== 'all')
    ? rawViolations.filter((v) => (v.severity || SEVERITY.MINOR).toLowerCase() === severityFilter)
    : (showViolations ? rawViolations : []);
  const bySeverity = (violationsBySeverity && (!severityFilter || severityFilter === 'all'))
    ? violationsBySeverity
    : groupBySeverity(filteredViolations);

  lines.push(...buildViolationsSection({ total: filteredViolations.length, bySeverity, severityFilter }));

  if (showCompliance) {
    lines.push(...buildComplianceSection(complianceList));
  }

  return lines.join('\n');
}
