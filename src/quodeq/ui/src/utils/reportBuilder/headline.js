// src/quodeq/ui/src/utils/reportBuilder/headline.js
//
// The report's headline line and since-baseline section, in the same order
// and words as the Overview hero. Like the rest of the export, the text is
// English markdown, not catalog strings.
import { EMPTY_VALUE_PLACEHOLDER } from './shared.js';

const SHORT_SHA = 7; // git's conventional abbreviation
const SCOPE_CHANGED = 'changed-files';
const SCOPE_MIXED = 'mixed';
const DENSITY_MISSING = '-';

function densityText(headline) {
  if (headline.density == null) return DENSITY_MISSING;
  const coverage = headline.coveragePct == null ? '' : ` (${headline.coveragePct}% coverage)`;
  return `${headline.density.toFixed(1)} per 100 files read${coverage}`;
}

/**
 * `**Majors:** 3 (0 critical) · **Open types:** 37 · **Score:** 9.0/10 Exemplary · **Density:** 32.3 per 100 files read (95% coverage)`
 * @param {{headline: Object|null, score: string, grade: string}} args
 */
export function buildHeadlineLine({ headline, score, grade }) {
  const scorePart = `**Score:** ${score} ${grade || EMPTY_VALUE_PLACEHOLDER}`;
  if (!headline) return scorePart;
  return [
    `**Majors:** ${headline.majors} (${headline.critical} critical)`,
    `**Open types:** ${headline.openTypes}`,
    scorePart,
    `**Density:** ${densityText(headline)}`,
  ].join(' · ');
}

function shortSha(sha) {
  return sha ? sha.slice(0, SHORT_SHA) : null;
}

function listOrNone(codes) {
  return codes.length > 0 ? codes.join(', ') : 'none';
}

function signed(n) {
  return n > 0 ? `+${n}` : String(n);
}

function isUnchanged(since) {
  return since.scope === SCOPE_CHANGED && since.changedFiles === 0 && since.majorsDelta === 0
    && since.typesClosed.length === 0 && since.typesOpened.length === 0;
}

function runsLine(since, currentSha) {
  if (since.scope === SCOPE_MIXED) return `against ${since.againstRunIds.length} baseline runs`;
  const from = shortSha(since.againstCommitShas[0]);
  const to = shortSha(currentSha);
  return from && to ? `run ${from} to ${to}` : 'run against the previous finished run';
}

function scopeLine(since) {
  if (since.scope !== SCOPE_CHANGED) return 'in all files (no commit recorded or the tree had uncommitted changes)';
  return `${since.changedFiles} files changed`;
}

/**
 * The `## Since baseline` section, or nothing without a baseline.
 * @param {Object|null} since the folded since-baseline summary
 * @param {string} [currentSha] the reported run's commit
 * @returns {string[]} markdown lines
 */
export function buildSinceBaselineSection(since, currentSha) {
  if (!since) return [];
  const lines = ['## Since baseline', '', `${runsLine(since, currentSha)} · ${scopeLine(since)}`, ''];
  if (isUnchanged(since)) {
    lines.push('No changes since the baseline.', '');
    return lines;
  }
  const newLabel = since.scope === SCOPE_CHANGED ? 'new in changed files' : 'new in all files';
  lines.push(`- majors ${signed(since.majorsDelta)} · types closed ${listOrNone(since.typesClosed)} · types opened ${listOrNone(since.typesOpened)}`);
  lines.push(`- ${newLabel} ${since.newCount} · resolved ${since.resolvedCount}`);
  lines.push('');
  return lines;
}
