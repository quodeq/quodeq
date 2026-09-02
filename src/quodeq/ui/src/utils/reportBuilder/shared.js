// src/quodeq/ui/src/utils/reportBuilder/shared.js
import { SEVERITY_ORDER } from '../formatters.js';

const SNIPPET_MAX_LINES = 5;

export function formatDate() {
  const d = new Date();
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return `${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear()}`;
}

export function capSnippet(snippet) {
  if (!snippet) return '';
  const lines = snippet.split('\n');
  if (lines.length <= SNIPPET_MAX_LINES) return snippet;
  return [...lines.slice(0, SNIPPET_MAX_LINES), `... (${lines.length - SNIPPET_MAX_LINES} more lines)`].join('\n');
}

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

export function groupBySeverity(violations) {
  const groups = {};
  for (const sev of SEVERITY_ORDER) groups[sev] = [];
  for (const v of violations) {
    const s = (v.severity || 'minor').toLowerCase();
    (groups[s] || (groups[s] = [])).push(v);
  }
  return groups;
}

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
