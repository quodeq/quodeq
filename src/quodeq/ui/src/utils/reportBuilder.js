// src/quodeq/ui/src/utils/reportBuilder.js
import { SEVERITY_ORDER } from './formatters.js';

const SNIPPET_MAX_LINES = 5;
const MAX_TOP_FILES = 15;

function formatDate() {
  const d = new Date();
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return `${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear()}`;
}

function capSnippet(snippet) {
  if (!snippet) return '';
  const lines = snippet.split('\n');
  if (lines.length <= SNIPPET_MAX_LINES) return snippet;
  return [...lines.slice(0, SNIPPET_MAX_LINES), `... (${lines.length - SNIPPET_MAX_LINES} more lines)`].join('\n');
}

function formatViolationEntry(v) {
  const lines = [];
  const principle = v.principle || '';
  const title = v.title || v.reason || 'Violation';
  lines.push(`#### [${principle}] ${title}`);
  if (v.file) {
    const fileRef = v.line != null ? `${v.file}:${v.line}` : v.file;
    lines.push(`- **File:** \`${fileRef}\``);
  }
  lines.push(`- **Severity:** ${v.severity || 'minor'}`);
  if (v.reason && v.reason !== title) lines.push(`- **Why:** ${v.reason}`);
  const refs = (v.reqRefs || []).filter((r) => r.url);
  if (refs.length > 0) {
    lines.push(`- **Refs:** ${refs.map((r) => `[${r.label}](${r.url})`).join(', ')}`);
  }
  const snippet = capSnippet(v.snippet);
  if (snippet) {
    lines.push('');
    lines.push('```');
    lines.push(snippet);
    lines.push('```');
  }
  lines.push('');
  return lines.join('\n');
}

function formatPrincipleTable(principleGrades) {
  const lines = [
    '| Principle | Score | Grade |',
    '|-----------|-------|-------|',
  ];
  for (const pg of principleGrades) {
    lines.push(`| ${pg.principle || '—'} | ${pg.score || '—'} | ${pg.grade || '—'} |`);
  }
  return lines.join('\n');
}

function groupBySeverity(violations) {
  const groups = {};
  for (const sev of SEVERITY_ORDER) groups[sev] = [];
  for (const v of violations) {
    const s = (v.severity || 'minor').toLowerCase();
    (groups[s] || (groups[s] = [])).push(v);
  }
  return groups;
}

function buildViolationsSection(allViolations) {
  const lines = [];
  const bySeverity = groupBySeverity(allViolations);
  lines.push(`## Violations (${allViolations.length})`);
  lines.push('');
  if (allViolations.length === 0) {
    lines.push('No violations found.');
    lines.push('');
  } else {
    for (const sev of SEVERITY_ORDER) {
      const vs = bySeverity[sev];
      if (!vs || vs.length === 0) continue;
      lines.push(`### ${sev.charAt(0).toUpperCase() + sev.slice(1)} (${vs.length})`);
      lines.push('');
      for (const v of vs) lines.push(formatViolationEntry(v));
    }
  }
  return lines;
}

function buildComplianceSection(compliance) {
  const lines = [];
  if (compliance.length === 0) return lines;
  const byPrinciple = {};
  for (const c of compliance) {
    const p = c.principle || 'Other';
    byPrinciple[p] = (byPrinciple[p] || 0) + 1;
  }
  lines.push(`## Compliance Summary (${compliance.length})`);
  lines.push('');
  lines.push('| Principle | Count |');
  lines.push('|-----------|-------|');
  for (const [p, count] of Object.entries(byPrinciple).sort((a, b) => b[1] - a[1])) {
    lines.push(`| ${p} | ${count} |`);
  }
  lines.push('');
  return lines;
}

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
    lines.push('> **Note:** Evaluation in progress — results may be incomplete.');
    lines.push('');
  }

  return lines.join('\n');
}

function buildDimensionSummaryTable(accumulatedDimensions) {
  const lines = [];
  if (accumulatedDimensions.length === 0) return lines;
  lines.push('## Dimensions');
  lines.push('');
  lines.push('| Dimension | Score | Grade | Violations | Compliance |');
  lines.push('|-----------|-------|-------|------------|------------|');
  for (const dim of accumulatedDimensions) {
    const name = (dim.dimension || '—').charAt(0).toUpperCase() + (dim.dimension || '').slice(1);
    const dScore = dim.overallScore || '—';
    const dGrade = dim.overallGrade || '—';
    const vCount = (dim.violations || []).length;
    const cCount = (dim.compliance || []).length;
    lines.push(`| ${name} | ${dScore} | ${dGrade} | ${vCount} | ${cCount} |`);
  }
  lines.push('');
  return lines;
}

function buildTopOffendingFiles(accumulatedDimensions) {
  const fileMap = {};
  for (const dim of accumulatedDimensions) {
    for (const v of (dim.violations || [])) {
      if (!v.file) continue;
      const f = v.file.split(':')[0];
      if (!fileMap[f]) fileMap[f] = { count: 0, critical: 0, major: 0, minor: 0 };
      fileMap[f].count++;
      const s = (v.severity || 'minor').toLowerCase();
      if (fileMap[f][s] !== undefined) fileMap[f][s]++;
    }
  }
  const topFiles = Object.entries(fileMap).sort((a, b) => b[1].count - a[1].count).slice(0, MAX_TOP_FILES);
  if (topFiles.length === 0) return [];
  const lines = [];
  lines.push('## Top Offending Files');
  lines.push('');
  lines.push('| File | Violations | Critical | Major | Minor |');
  lines.push('|------|-----------|----------|-------|-------|');
  for (const [file, stats] of topFiles) {
    lines.push(`| ${file} | ${stats.count} | ${stats.critical} | ${stats.major} | ${stats.minor} |`);
  }
  lines.push('');
  return lines;
}

function buildCritMajorSection(accumulatedDimensions) {
  const lines = [];
  const critMajor = [];
  for (const dim of accumulatedDimensions) {
    const vs = (dim.violations || []).filter((v) => v.severity === 'critical' || v.severity === 'major');
    if (vs.length > 0) critMajor.push({ dimension: dim.dimension, violations: vs });
  }
  if (critMajor.length > 0) {
    const total = critMajor.reduce((sum, d) => sum + d.violations.length, 0);
    lines.push(`## Critical & Major Violations (${total})`);
    lines.push('');
    for (const { dimension, violations } of critMajor) {
      lines.push(`### ${(dimension || '').toLowerCase()}`);
      lines.push('');
      for (const v of violations) lines.push(formatViolationEntry(v));
    }
  } else {
    lines.push('## Critical & Major Violations');
    lines.push('');
    lines.push('No critical or major violations found.');
    lines.push('');
  }
  return lines;
}

function buildOverviewSummarySection(summary, accumulatedDimensions) {
  const sev = summary.severity || {};
  const lines = [];
  lines.push('## Summary');
  lines.push('');
  lines.push(`- **${accumulatedDimensions.length}** dimensions evaluated`);
  lines.push(`- **${summary.totalViolations || 0}** total violations (${sev.critical || 0} critical, ${sev.major || 0} major, ${sev.minor || 0} minor)`);
  lines.push(`- **${summary.totalCompliance || 0}** compliance findings`);
  const ratio = (summary.totalViolations && summary.totalCompliance)
    ? `1:${Math.round(summary.totalCompliance / summary.totalViolations)}`
    : '—';
  lines.push(`- **Ratio:** ${ratio}`);
  lines.push('');
  return lines;
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

export function buildPrincipleReport({ principle, dimension, score, grade, violations, violationsBySeverity, compliance, principleData, runId, dateLabel }) {
  const violationsList = violations || [];
  const complianceList = (compliance || []).filter((c) => c.file || c.reason || c.snippet);
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

  const bySeverity = violationsBySeverity || groupBySeverity(violationsList);
  lines.push(`## Violations (${violationsList.length})`);
  lines.push('');
  if (violationsList.length === 0) {
    lines.push('No violations found.');
    lines.push('');
  } else {
    for (const sev of SEVERITY_ORDER) {
      const vs = bySeverity[sev] || [];
      if (vs.length === 0) continue;
      lines.push(`### ${sev.charAt(0).toUpperCase() + sev.slice(1)} (${vs.length})`);
      lines.push('');
      for (const v of vs) lines.push(formatViolationEntry(v));
    }
  }

  lines.push(...buildComplianceSection(complianceList));

  return lines.join('\n');
}

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

function buildFileViolationsSection(file) {
  const lines = [];
  const allViolations = SEVERITY_ORDER.flatMap((sev) => file.violationsBySeverity?.[sev] || []);
  lines.push(`## Violations (${allViolations.length})`);
  lines.push('');
  if (allViolations.length === 0) {
    lines.push('No violations found.');
    lines.push('');
    return lines;
  }
  for (const sev of SEVERITY_ORDER) {
    const vs = file.violationsBySeverity?.[sev] || [];
    if (vs.length === 0) continue;
    lines.push(`### ${sev.charAt(0).toUpperCase() + sev.slice(1)} (${vs.length})`);
    lines.push('');
    for (const v of vs) lines.push(formatViolationEntry(v));
  }
  return lines;
}

export function buildFileReport(file) {
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
  lines.push(...buildFileViolationsSection(file));
  lines.push(...buildComplianceSection(file?.compliance || []));

  return lines.join('\n');
}
