// src/quodeq/ui/src/utils/reportBuilder/principleBuilder.js
import { SEVERITY_ORDER } from '../formatters.js';
import { formatDate, formatViolationEntry, groupBySeverity, buildComplianceSection } from './shared.js';

function buildPrincipleHeaderSection({ principle, dimension, score, grade, runId, dateLabel, principleData }) {
  const date = dateLabel || formatDate();
  const ridSuffix = runId ? ` · **Run:** ${runId.slice(0, 8)}` : '';
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

function buildPrincipleViolationsSection({ filteredViolations, bySeverity, severityFilter }) {
  const lines = [];
  lines.push(`## Violations (${filteredViolations.length})`);
  lines.push('');
  if (filteredViolations.length === 0) {
    lines.push('No violations found.');
    lines.push('');
  } else {
    for (const sev of SEVERITY_ORDER) {
      if (severityFilter && severityFilter !== 'all' && severityFilter !== sev) continue;
      const vs = bySeverity[sev] || [];
      if (vs.length === 0) continue;
      lines.push(`### ${sev.charAt(0).toUpperCase() + sev.slice(1)} (${vs.length})`);
      lines.push('');
      for (const v of vs) lines.push(formatViolationEntry(v));
    }
  }
  return lines;
}

export function buildPrincipleReport({ principle, dimension, score, grade, violations, violationsBySeverity, compliance, principleData, runId, dateLabel, severityFilter }) {
  const rawViolations = violations || [];
  const complianceList = (compliance || []).filter((c) => c.file || c.reason || c.snippet);

  const lines = buildPrincipleHeaderSection({ principle, dimension, score, grade, runId, dateLabel, principleData });

  const showViolations = severityFilter !== 'compliance';
  const showCompliance = !severityFilter || severityFilter === 'all' || severityFilter === 'compliance';

  const filteredViolations = (showViolations && severityFilter && severityFilter !== 'all')
    ? rawViolations.filter((v) => (v.severity || 'minor').toLowerCase() === severityFilter)
    : (showViolations ? rawViolations : []);
  const bySeverity = (violationsBySeverity && (!severityFilter || severityFilter === 'all'))
    ? violationsBySeverity
    : groupBySeverity(filteredViolations);

  lines.push(...buildPrincipleViolationsSection({ filteredViolations, bySeverity, severityFilter }));

  if (showCompliance) {
    lines.push(...buildComplianceSection(complianceList));
  }

  return lines.join('\n');
}
