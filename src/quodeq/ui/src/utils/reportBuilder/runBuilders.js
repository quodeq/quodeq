// src/quodeq/ui/src/utils/reportBuilder/runBuilders.js
import {
  formatDate, formatScore, buildViolationsSection, buildComplianceSection, groupBySeverity,
  runSuffix, EMPTY_VALUE_PLACEHOLDER, formatPrincipleTable,
} from './shared.js';
import {
  buildDimensionSummaryTable,
  buildTopOffendingFiles,
  buildCritMajorSection,
  buildOverviewSummarySection,
} from './dimensionSummary.js';

/**
 * The full Markdown report for one dimension of one run.
 *
 * @returns {string}
 */
export function buildDimensionReport({ evalData, principleGrades, allViolations, overallGrade, dateLabel, runId }) {
  const dim = (evalData?.dimension || 'unknown').toLowerCase();
  const score = overallGrade?.score || EMPTY_VALUE_PLACEHOLDER;
  const grade = overallGrade?.grade || EMPTY_VALUE_PLACEHOLDER;
  const compliance = evalData?.compliance || [];
  const date = dateLabel || formatDate();
  const rid = runSuffix(runId);

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

  lines.push(...buildViolationsSection({ total: allViolations.length, bySeverity: groupBySeverity(allViolations) }));
  lines.push(...buildComplianceSection(compliance));

  if (evalData?.partial) {
    lines.push('> **Note:** Evaluation in progress. Results may be incomplete.');
    lines.push('');
  }

  return lines.join('\n');
}

// The cross-dimension report body shared by the overview and run reports:
// title, the date/run/score line, then the same four sections in the same
// order. Only the header wording and where the numbers come from differ.
function buildScoredReport({ title, dateLabel, rid, score, grade, summary, dimensions }) {
  const lines = [];
  lines.push(`# ${title}`);
  lines.push('');
  lines.push(`**Date:** ${dateLabel}${rid} · **Overall Score:** ${score} ${grade}`);
  lines.push('');

  lines.push(...buildDimensionSummaryTable(dimensions));
  lines.push(...buildTopOffendingFiles(dimensions));
  lines.push(...buildCritMajorSection(dimensions));
  lines.push(...buildOverviewSummarySection(summary, dimensions));

  return lines.join('\n');
}

/**
 * The full Markdown report for a project's accumulated scores, across every
 * dimension.
 *
 * @returns {string}
 */
export function buildOverviewReport(accumulated, accumulatedDimensions, projectName) {
  const summary = accumulated?.summary || {};
  return buildScoredReport({
    title: `${projectName || 'Project'} report`,
    dateLabel: formatDate(),
    rid: '',
    score: formatScore(summary.numericAverage),
    grade: summary.overallGrade || EMPTY_VALUE_PLACEHOLDER,
    summary,
    dimensions: accumulatedDimensions,
  });
}

/**
 * The full Markdown report for a single run, dimension by dimension.
 *
 * @returns {string}
 */
export function buildRunReport({ dashboard, runSummary, projectName }) {
  const selectedRun = dashboard?.selectedRun || {};
  return buildScoredReport({
    title: `${projectName || 'Run'} run report`,
    dateLabel: selectedRun.dateLabel || formatDate(),
    rid: runSuffix(selectedRun.runId || ''),
    score: formatScore(runSummary?.numericAverage),
    grade: runSummary?.overallGrade || EMPTY_VALUE_PLACEHOLDER,
    summary: runSummary || {},
    dimensions: dashboard?.dimensions || [],
  });
}
