// src/quodeq/ui/src/utils/reportBuilder/shared.js
import { SEVERITY_ORDER } from '../formatters.js';

const SNIPPET_MAX_LINES = 5;
// Short run-id shown in report headers ("**Run:** 3f9c1a2b").
export const RUN_ID_DISPLAY_LENGTH = 8;
// Fallback for a score/grade the payload doesn't carry.
export const EMPTY_VALUE_PLACEHOLDER = '—';

/**
 * Today as "3 Jul 2026", the date stamp every report header carries.
 */
export function formatDate() {
  const d = new Date();
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return `${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear()}`;
}

/**
 * An overall score as the report headers write it: one decimal out of ten,
 * or an em dash when there is none. Accepts the number the accumulated
 * summary carries and the numeric string a run summary carries.
 *
 * @param {number|string|null|undefined} value
 * @returns {string}
 */
export function formatScore(value) {
  if (value == null) return '\u2014';
  return `${Math.round(parseFloat(value) * 10) / 10}/10`;
}

/**
 * Truncates a code snippet to the first few lines, appending a count of what
 * was dropped, so one huge finding cannot dominate a report.
 */
export function capSnippet(snippet) {
  if (!snippet) return '';
  const lines = snippet.split('\n');
  if (lines.length <= SNIPPET_MAX_LINES) return snippet;
  return [...lines.slice(0, SNIPPET_MAX_LINES), `... (${lines.length - SNIPPET_MAX_LINES} more lines)`].join('\n');
}

/**
 * One violation as a Markdown block: heading, file ref, severity, reason and
 * requirement links.
 *
 * @returns {string}
 */
export function formatViolationEntry(v) {
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

/**
 * The principle/score/grade Markdown table.
 *
 * @returns {string}
 */
export function formatPrincipleTable(principleGrades) {
  const lines = [
    '| Principle | Score | Grade |',
    '|-----------|-------|-------|',
  ];
  for (const pg of principleGrades) {
    lines.push(`| ${pg.principle || '—'} | ${pg.score || '—'} | ${pg.grade || '—'} |`);
  }
  return lines.join('\n');
}

/**
 * Buckets violations by severity, with every known severity present as an
 * empty array so callers can iterate SEVERITY_ORDER without guarding.
 */
export function groupBySeverity(violations) {
  const groups = {};
  for (const sev of SEVERITY_ORDER) groups[sev] = [];
  for (const v of violations) {
    const s = (v.severity || 'minor').toLowerCase();
    (groups[s] || (groups[s] = [])).push(v);
  }
  return groups;
}

/**
 * The "Violations" section, severity by severity. Returns the Markdown lines
 * (not a joined string) so callers can splice sections together.
 *
 * @returns {string[]}
 */
export function buildViolationsSection(allViolations) {
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

/**
 * The compliance count-per-principle section, or no lines at all when there
 * is nothing compliant to report.
 *
 * @returns {string[]}
 */
export function buildComplianceSection(compliance) {
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
