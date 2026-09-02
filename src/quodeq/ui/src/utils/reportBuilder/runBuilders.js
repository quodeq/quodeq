// src/quodeq/ui/src/utils/reportBuilder/runBuilders.js
import { formatDate, buildViolationsSection, buildComplianceSection } from './shared.js';
import {
  buildDimensionSummaryTable,
  buildTopOffendingFiles,
  buildCritMajorSection,
  buildOverviewSummarySection,
} from './dimensionSummary.js';
import { formatPrincipleTable } from './shared.js';

export function buildDimensionReport({ evalData, principleGrades, allViolations, overallGrade, dateLabel, runId }) {
  const dim = (evalData?.dimension || 'unknown').toLowerCase();
  const score = overallGrade?.score || '—';
  const grade = overallGrade?.grade || '—';
  const compliance = evalData?.compliance || [];
  const date = dateLabel || formatDate();
  const rid = runId ? ` · **Run:** ${runId.slice(0, 8)}` : '';

  const lines = [];
  lines.push(`# ${dim} report`);
  lines.push('');
  lines.push(`**Date:** ${date}${rid} · **Score:** ${score} ${grade}`);
  lines.push('');

  if (principleGrades.length > 0) {
    lines.push('## Principle Scores');
    lines.push('');
    lines.push(formatPrincipleTable(principleGrades));
    lines.push('');
  }

  lines.push(...buildViolationsSection(allViolations));
  lines.push(...buildComplianceSection(compliance));

  if (evalData?.partial) {
    lines.push('> **Note:** Evaluation in progress. Results may be incomplete.');
    lines.push('');
  }

  return lines.join('\n');
}

export function buildOverviewReport(accumulated, accumulatedDimensions, projectName) {
  const summary = accumulated?.summary || {};
  const score = summary.numericAverage != null ? `${Math.round(summary.numericAverage * 10) / 10}/10` : '—';
  const grade = summary.overallGrade || '—';
  const date = formatDate();
  const project = projectName || 'Project';

  const lines = [];
  lines.push(`# ${project} report`);
  lines.push('');
  lines.push(`**Date:** ${date} · **Overall Score:** ${score} ${grade}`);
  lines.push('');

  lines.push(...buildDimensionSummaryTable(accumulatedDimensions));
  lines.push(...buildTopOffendingFiles(accumulatedDimensions));
  lines.push(...buildCritMajorSection(accumulatedDimensions));
  lines.push(...buildOverviewSummarySection(summary, accumulatedDimensions));

  return lines.join('\n');
}

export function buildRunReport({ dashboard, runSummary, projectName }) {
  const dimensions = dashboard?.dimensions || [];
  const selectedRun = dashboard?.selectedRun || {};
  const dateLabel = selectedRun.dateLabel || formatDate();
  const runId = selectedRun.runId || '';
  const numeric = runSummary?.numericAverage;
  const score = numeric != null ? `${Math.round(parseFloat(numeric) * 10) / 10}/10` : '—';
  const grade = runSummary?.overallGrade || '—';
  const project = projectName || 'Run';
  const ridSuffix = runId ? ` · **Run:** ${runId.slice(0, 8)}` : '';

  const lines = [];
  lines.push(`# ${project} run report`);
  lines.push('');
  lines.push(`**Date:** ${dateLabel}${ridSuffix} · **Overall Score:** ${score} ${grade}`);
  lines.push('');

  lines.push(...buildDimensionSummaryTable(dimensions));
  lines.push(...buildTopOffendingFiles(dimensions));
  lines.push(...buildCritMajorSection(dimensions));
  lines.push(...buildOverviewSummarySection(runSummary || {}, dimensions));

  return lines.join('\n');
}
