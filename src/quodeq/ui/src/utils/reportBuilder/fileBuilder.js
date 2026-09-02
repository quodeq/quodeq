// src/quodeq/ui/src/utils/reportBuilder/fileBuilder.js
import { SEVERITY_ORDER } from '../formatters.js';
import { formatDate, formatViolationEntry, buildComplianceSection } from './shared.js';

function buildFileSummarySection(file, totalViolations, totalCompliance) {
  const lines = [];
  lines.push('## Summary');
  lines.push('');
  lines.push(`- **${totalViolations}** total violations (${file.critical || 0} critical, ${file.major || 0} major, ${file.minor || 0} minor)`);
  lines.push(`- **${totalCompliance}** compliance findings`);
  lines.push(`- **${file.dimensionsCount || 0}** dimension${file.dimensionsCount === 1 ? '' : 's'}`);
  if (totalViolations && totalCompliance) {
    lines.push(`- **Ratio:** 1:${Math.round(totalCompliance / totalViolations)}`);
  }
  lines.push('');
  return lines;
}

function buildFileViolationsSection(file, severityFilter) {
  const lines = [];
  const allViolations = SEVERITY_ORDER
    .filter((sev) => !severityFilter || severityFilter === 'all' || severityFilter === sev)
    .flatMap((sev) => file.violationsBySeverity?.[sev] || []);
  lines.push(`## Violations (${allViolations.length})`);
  lines.push('');
  if (allViolations.length === 0) {
    lines.push('No violations found.');
    lines.push('');
    return lines;
  }
  for (const sev of SEVERITY_ORDER) {
    if (severityFilter && severityFilter !== 'all' && severityFilter !== sev) continue;
    const vs = file.violationsBySeverity?.[sev] || [];
    if (vs.length === 0) continue;
    lines.push(`### ${sev.charAt(0).toUpperCase() + sev.slice(1)} (${vs.length})`);
    lines.push('');
    for (const v of vs) lines.push(formatViolationEntry(v));
  }
  return lines;
}

export function buildFileReport(file, severityFilter) {
  const filePath = file?.file || 'unknown';
  const totalViolations = file?.total || 0;
  const totalCompliance = file?.compliance?.length || 0;
  const date = formatDate();

  const lines = [];
  lines.push(`# File report`);
  lines.push('');
  lines.push(`**File:** \`${filePath}\` · **Date:** ${date}`);
  lines.push('');

  lines.push(...buildFileSummarySection(file, totalViolations, totalCompliance));

  const showCompliance = !severityFilter || severityFilter === 'all' || severityFilter === 'compliance';

  lines.push(...buildFileViolationsSection(file, severityFilter));
  if (showCompliance) lines.push(...buildComplianceSection(file?.compliance || []));

  return lines.join('\n');
}
