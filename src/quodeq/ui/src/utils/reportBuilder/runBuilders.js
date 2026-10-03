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
import { buildTilesLine, buildStripLine, buildSinceBaselineSection } from './headline.js';

/**
 * The full Markdown report for one dimension of one run.
 *
 * @param {object} args
 * @param {{dimension: string, compliance: Array, partial: boolean}} args.evalData
 * @param {Array} args.principleGrades - rows of the principle-scores table;
 *   an empty array drops the section.
 * @param {Array} args.allViolations - grouped by severity for the report.
 * @param {{score: number, grade: string}} args.overallGrade
 * @param {string} [args.dateLabel] - defaults to today.
 * @param {string} [args.runId] - shown beside the date when present.
 * @returns {string}
 */
export function buildDimensionReport({ evalData, principleGrades, allViolations, overallGrade, dateLabel, runId }) {
  const dim = (evalData?.dimension || 'unknown').toLowerCase();
  const score = overallGrade?.score ?? EMPTY_VALUE_PLACEHOLDER;
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
// title, the date/run line, the Overview's tiles line (score, violations,
// compliance, ratio), its strip line (critical, majors, open types, density),
// the since-baseline section, then the same four sections in the same order.
// The raw violations total stays in the summary at the end. Only the header
// wording and where the numbers come from differ.
function buildScoredReport({ title, dateLabel, rid, score, grade, summary, dimensions, headline, since, commitSha }) {
  const lines = [];
  lines.push(`# ${title}`);
  lines.push('');
  lines.push(`**Date:** ${dateLabel}${rid}`);
  lines.push('');
  lines.push(buildTilesLine({ summary, score, grade }));
  const strip = buildStripLine(headline);
  if (strip) lines.push('', strip);
  lines.push('');
  lines.push(...buildSinceBaselineSection(since, commitSha));

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
 * @param {{score: number, grade: string, summary: Object}} accumulated
 * @param {Array} accumulatedDimensions - per-dimension scores and findings.
 * @param {string} projectName - the report's title.
 * @param {{headline?: Object|null, since?: Object|null, commitSha?: string}} [extras] - the strip's
 *   headline numbers and the folded since-baseline summary, when the caller has them.
 * @returns {string}
 */
export function buildOverviewReport(accumulated, accumulatedDimensions, projectName, extras = {}) {
  const summary = accumulated?.summary || {};
  return buildScoredReport({
    title: `${projectName || 'Project'} report`,
    dateLabel: formatDate(),
    rid: '',
    score: formatScore(summary.numericAverage),
    grade: summary.overallGrade || EMPTY_VALUE_PLACEHOLDER,
    summary,
    dimensions: accumulatedDimensions,
    headline: extras.headline || null,
    since: extras.since || null,
    commitSha: extras.commitSha,
  });
}

/**
 * The full Markdown report for a single run, dimension by dimension.
 *
 * @param {object} args
 * @param {object} args.dashboard - the run's dashboard payload.
 * @param {object} args.runSummary - the run's header numbers.
 * @param {string} args.projectName - the report's title.
 * @param {Object|null} [args.headline] - the strip's headline numbers.
 * @param {Object|null} [args.since] - the folded since-baseline summary.
 * @returns {string}
 */
export function buildRunReport({ dashboard, runSummary, projectName, headline = null, since = null }) {
  const selectedRun = dashboard?.selectedRun || {};
  return buildScoredReport({
    title: `${projectName || 'Run'} run report`,
    dateLabel: selectedRun.dateLabel || formatDate(),
    rid: runSuffix(selectedRun.runId || ''),
    score: formatScore(runSummary?.numericAverage),
    grade: runSummary?.overallGrade || EMPTY_VALUE_PLACEHOLDER,
    summary: runSummary || {},
    dimensions: dashboard?.dimensions || [],
    headline,
    since,
    commitSha: selectedRun.commitSha,
  });
}
