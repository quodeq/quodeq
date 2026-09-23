// src/quodeq/ui/src/utils/reportBuilder/dimensionSummary.js
import { formatViolationEntry } from './shared.js';
import { complianceRatio } from '../textFormatting.js';
import { SEVERITY } from '../../vocab/severity.js';

const MAX_TOP_FILES = 15;

/**
 * The per-dimension score/grade/counts table, or no lines when no dimension
 * has been evaluated.
 *
 * @param {Array<{dimension: string, overallScore: number, overallGrade: string,
 *   violations: Array, compliance: Array}>} accumulatedDimensions
 * @returns {string[]}
 */
export function buildDimensionSummaryTable(accumulatedDimensions) {
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

/**
 * The worst-offending-files table across every dimension, capped at
 * MAX_TOP_FILES rows.
 *
 * @param {Array<{violations: Array}>} accumulatedDimensions - files are keyed
 *   by each violation's `file`, so a file counts once across all dimensions.
 * @returns {string[]}
 */
export function buildTopOffendingFiles(accumulatedDimensions) {
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

/**
 * The critical-and-major section, grouped by dimension. Always returns a
 * heading, saying so explicitly when there is nothing at those severities.
 *
 * @param {Array<{dimension: string, violations: Array}>} accumulatedDimensions
 * @returns {string[]}
 */
export function buildCritMajorSection(accumulatedDimensions) {
  const lines = [];
  const critMajor = [];
  for (const dim of accumulatedDimensions) {
    const vs = (dim.violations || []).filter((v) => v.severity === SEVERITY.CRITICAL || v.severity === SEVERITY.MAJOR);
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

/**
 * The headline counts (dimensions, violations by severity, compliance and
 * the compliance ratio) that close an overview report.
 *
 * @param {{severity: Object, totalViolations: number, totalCompliance: number}} summary
 *   the already-rolled-up counts.
 * @param {Array} accumulatedDimensions - used only for the dimension count.
 * @returns {string[]}
 */
export function buildOverviewSummarySection(summary, accumulatedDimensions) {
  const sev = summary.severity || {};
  const lines = [];
  lines.push('## Summary');
  lines.push('');
  lines.push(`- **${accumulatedDimensions.length}** dimensions evaluated`);
  lines.push(`- **${summary.totalViolations || 0}** total violations (${sev.critical || 0} critical, ${sev.major || 0} major, ${sev.minor || 0} minor)`);
  lines.push(`- **${summary.totalCompliance || 0}** compliance findings`);
  const ratio = complianceRatio(summary.totalViolations || 0, summary.totalCompliance || 0);
  lines.push(`- **Ratio:** ${ratio}`);
  lines.push('');
  return lines;
}
