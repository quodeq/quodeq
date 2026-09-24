// src/quodeq/ui/src/utils/reportBuilder/fileBuilder.js
import { KNOWN_SEVERITIES } from '../constants.js';
import { formatDate, buildComplianceSection, buildViolationsSection, severityMatches, showsCompliance } from './shared.js';
import { complianceRatio } from '../textFormatting.js';

function buildFileSummarySection(file, totalViolations, totalCompliance) {
  const lines = [];
  lines.push('## Summary');
  lines.push('');
  lines.push(`- **${totalViolations}** total violations (${file.critical || 0} critical, ${file.major || 0} major, ${file.minor || 0} minor)`);
  lines.push(`- **${totalCompliance}** compliance findings`);
  lines.push(`- **${file.dimensionsCount || 0}** dimension${file.dimensionsCount === 1 ? '' : 's'}`);
  lines.push(`- **Ratio:** ${complianceRatio(totalViolations, totalCompliance)}`);
  lines.push('');
  return lines;
}

function buildFileViolationsSection(file, severityFilter) {
  const total = KNOWN_SEVERITIES
    .filter((sev) => severityMatches(severityFilter, sev))
    .reduce((n, sev) => n + (file.violationsBySeverity?.[sev] || []).length, 0);
  return buildViolationsSection({ total, bySeverity: file.violationsBySeverity, severityFilter });
}

/**
 * The full Markdown report for one file. `severityFilter` narrows it to what
 * the user is currently looking at, so the report matches the screen.
 *
 * @param {{file: string, total: number, dimensionsCount: number,
 *   violationsBySeverity: Object, compliance: Array}} file
 * @param {string} [severityFilter] - absent or 'all' keeps everything;
 *   'compliance' keeps only the compliance section.
 * @returns {string}
 */
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

  lines.push(...buildFileViolationsSection(file, severityFilter));
  if (showsCompliance(severityFilter)) lines.push(...buildComplianceSection(file?.compliance || []));

  return lines.join('\n');
}
