// src/quodeq/ui/src/utils/reportBuilder/headline.js
//
// The report's opening lines in the Overview's order: the four tiles, then
// the convergence strip, then the since-baseline section. Like the rest of
// the export, the text is English markdown, not catalog strings. Counts only:
// requirement codes never appear here (the Violations by-type tab lists them).
import { EMPTY_VALUE_PLACEHOLDER } from './shared.js';
import { complianceRatio } from '../textFormatting.js';
import { isUnchangedSince } from '../../features/dashboard/headlineStats.js';

const SHORT_SHA = 7; // git's conventional abbreviation
const SCOPE_CHANGED = 'changed-files';
const SCOPE_MIXED = 'mixed';
const DENSITY_MISSING = 'not available (no files-read count)';
const SEPARATOR = ' · ';

function isCount(v) {
  return typeof v === 'number';
}

/**
 * `**Score:** 9.0/10 Exemplary · **Violations:** 1738 · **Compliance:** 2207 · **Ratio:** 1:1`
 * The totals follow the score only when the summary carries them.
 * @param {{summary: Object, score: string, grade: string}} args
 */
export function buildTilesLine({ summary, score, grade }) {
  const parts = [`**Score:** ${score} ${grade || EMPTY_VALUE_PLACEHOLDER}`];
  const { totalViolations, totalCompliance } = summary || {};
  if (isCount(totalViolations)) parts.push(`**Violations:** ${totalViolations}`);
  if (isCount(totalCompliance)) parts.push(`**Compliance:** ${totalCompliance}`);
  if (isCount(totalViolations) && isCount(totalCompliance)) {
    parts.push(`**Ratio:** ${complianceRatio(totalViolations, totalCompliance)}`);
  }
  return parts.join(SEPARATOR);
}

function densityText(headline) {
  if (headline.density == null) return DENSITY_MISSING;
  const coverage = headline.coveragePct == null ? '' : ` (${headline.coveragePct}% coverage)`;
  return `${headline.density.toFixed(1)} per 100 files read${coverage}`;
}

/**
 * `**Critical:** 0 · **Majors:** 3 · **Open types:** 37 · **Density:** 68.8 per 100 files read (95% coverage)`,
 * or nothing without a headline. Majors are major only, as on the strip
 * (buildHeadline's `majors` counts critical + major).
 * @param {Object|null} headline buildHeadline()'s output
 */
export function buildStripLine(headline) {
  if (!headline) return '';
  return [
    `**Critical:** ${headline.critical}`,
    `**Majors:** ${headline.majors - headline.critical}`,
    `**Open types:** ${headline.openTypes}`,
    `**Density:** ${densityText(headline)}`,
  ].join(SEPARATOR);
}

function shortSha(sha) {
  return sha ? sha.slice(0, SHORT_SHA) : null;
}

function signed(n) {
  return n > 0 ? `+${n}` : String(n);
}

function runsLine(since, currentSha) {
  if (since.scope === SCOPE_MIXED) return `against ${since.againstRunIds.length} baseline runs`;
  const from = shortSha(since.againstCommitShas[0]);
  const to = shortSha(currentSha);
  return from && to ? `run ${from} to ${to}` : 'run against the previous finished run';
}

function scopeLine(since) {
  if (since.scope === SCOPE_MIXED) return 'in all files (baselines differ per dimension)';
  if (since.scope !== SCOPE_CHANGED) return 'in all files (no commit recorded or the tree had uncommitted changes)';
  return `${since.changedFiles} files changed`;
}

/**
 * The `## Since baseline` section, or nothing without a baseline.
 * @param {Object|null} since the folded since-baseline summary (sumSinceBaseline)
 * @param {string} [currentSha] the reported run's commit
 * @returns {string[]} markdown lines
 */
export function buildSinceBaselineSection(since, currentSha) {
  if (!since) return [];
  const lines = ['## Since baseline', '', `${runsLine(since, currentSha)}${SEPARATOR}${scopeLine(since)}`, ''];
  if (isUnchangedSince(since)) {
    lines.push('No changes since the baseline.', '');
    return lines;
  }
  const newLabel = since.scope === SCOPE_CHANGED ? 'new in changed files' : 'new in all files';
  lines.push(`- majors ${signed(since.majorsDelta)}${SEPARATOR}types closed ${since.typesClosed.length}${SEPARATOR}types opened ${since.typesOpened.length}`);
  lines.push(`- ${newLabel} ${since.newCount}${SEPARATOR}resolved ${since.resolvedCount}`);
  lines.push('');
  return lines;
}
