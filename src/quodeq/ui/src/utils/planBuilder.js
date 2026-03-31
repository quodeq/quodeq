import { SEVERITY_ORDER } from './formatters.js';

const PLAN_SNIPPET_MAX_LINES = 5;

/**
 * Cap a code snippet for plan output — show only the first few lines.
 */
function capSnippet(snippet) {
  if (!snippet) return snippet;
  const lines = snippet.split('\n');
  if (lines.length <= PLAN_SNIPPET_MAX_LINES) return snippet;
  return [...lines.slice(0, PLAN_SNIPPET_MAX_LINES), `... (${lines.length - PLAN_SNIPPET_MAX_LINES} more lines)`].join('\n');
}
import {
  PLAN_SYSTEM_PREAMBLE,
  PLAN_OUTPUT_INSTRUCTIONS,
  GROUP_PLAN_PREAMBLE,
  GROUP_PLAN_OUTPUT,
  FIX_HINTS,
} from './planConstants.js';

// ---------------------------------------------------------------------------
// Plan text constants (authoritative home — re-exported by explorerUtils.js)
// ---------------------------------------------------------------------------

export const PLAN_TEST_INSTRUCTION_GROUP =
  'After completing each group of related fixes, run the full test suite (`npm test` / `pytest` / the project\'s test command). If tests fail, diagnose and fix the breakage before moving on. Only modify a test if it was explicitly asserting the exact pattern you just changed — state your reasoning before editing any test file.';

export const PLAN_TEST_INSTRUCTION_SINGLE =
  'After applying this fix, run the full test suite. If tests fail, diagnose and fix the breakage before moving on. Only modify a test if it was explicitly asserting the exact pattern you just changed — state your reasoning before editing any test file.';

export const PLAN_COMPLETION_CHECKLIST = [
  '---', '',
  '## Completion checklist', '',
  'Before claiming this plan is done, verify:', '',
  '- [ ] **Every violation has a code change.** Count your diffs — the number must match the total violations above. A comment or docstring is NOT a fix unless the violation specifically requires documentation.',
  '- [ ] **No violations were skipped.** If a violation cannot be fixed, state why explicitly — do not silently omit it.',
  '- [ ] **Tests pass.** Run the full test suite after all changes.',
  '- [ ] **Verify metrics.** For each function-length or file-length violation, confirm the result is within limits (e.g., `wc -l`, AST line count).',
].join('\n');

export { FIX_HINTS };

export function getFixHint(req) {
  if (!req) return null;
  if (FIX_HINTS[req]) return FIX_HINTS[req];
  const prefix = req.replace(/-\d+$/, '');
  return FIX_HINTS[prefix] || null;
}

// ---------------------------------------------------------------------------
// Internal constants used by plan builders
// ---------------------------------------------------------------------------

const KNOWN_SEVERITIES = ['critical', 'major', 'minor', 'unknown'];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function normalizeSeverity(value) {
  const normalized = String(value || 'unknown').toLowerCase();
  return KNOWN_SEVERITIES.includes(normalized) ? normalized : 'unknown';
}

/** Collect unique files touched by violations. */
function collectAffectedFiles(violations) {
  const files = new Set();
  violations.forEach((v) => { if (v.file) files.add(v.file); });
  return Array.from(files).sort();
}

/** Render a single violation entry as markdown lines. */
function renderViolationEntry(v, index, { principleKey, reasonKey }) {
  const lines = [];
  const loc = v.file ? ` — \`${v.file}${v.line ? `:${v.line}` : ''}\`` : '';
  const principle = v[principleKey] || 'Violation';
  const reason = v[reasonKey];

  lines.push(`### ${index + 1}. ${principle}${loc}`);

  if (reason) {
    lines.push('', `**Why it's a violation:** ${reason}`);
  }

  const hint = getFixHint(v.req);
  if (hint) {
    lines.push('', `**Expected fix:** ${hint}`);
  }

  if (v.cwe) {
    lines.push('', `**Reference:** CWE-${v.cwe}`);
  }

  if (v.snippet) {
    lines.push('', '**Affected code:**');
    lines.push('```');
    v.snippet.split('\n').forEach((l) => lines.push(l));
    lines.push('```');
  }

  lines.push('');
  return lines;
}

function _buildPlanLines(dimName, totalCount, bySeverity, allViolations, entryKeys) {
  const affectedFiles = collectAffectedFiles(allViolations);
  const lines = [
    ...PLAN_SYSTEM_PREAMBLE, '',
    `# Fix Plan: ${dimName} dimension`, '',
    `**Total violations:** ${totalCount}`,
  ];
  if (affectedFiles.length > 0) {
    lines.push('', `**Files you will modify** (${affectedFiles.length}):`);
    affectedFiles.forEach((f) => lines.push(`- \`${f}\``));
  }
  lines.push('', '---', '');
  KNOWN_SEVERITIES.forEach((sev) => {
    const vs = bySeverity[sev];
    if (!vs || vs.length === 0) return;
    lines.push(`## ${sev.charAt(0).toUpperCase() + sev.slice(1)} violations (${vs.length})`, '');
    vs.forEach((v, i) => lines.push(...renderViolationEntry(v, i, entryKeys)));
  });
  lines.push(...PLAN_OUTPUT_INSTRUCTIONS);
  lines.push(PLAN_TEST_INSTRUCTION_GROUP);
  lines.push('', PLAN_COMPLETION_CHECKLIST);
  return lines.join('\n').trim();
}

// ---------------------------------------------------------------------------
// Dimension plan builders (used by explorerUtils re-exports)
// ---------------------------------------------------------------------------

export function buildDimensionPlanText(evalData) {
  const bySeverity = {};
  let total = 0;
  (evalData.principles || []).forEach((principle) => {
    (principle.violations || []).forEach((v) => {
      const sev = normalizeSeverity(v.severity);
      if (!bySeverity[sev]) bySeverity[sev] = [];
      bySeverity[sev].push({ ...v, _principle: principle.name, _findings: principle.findings });
      total++;
    });
  });
  if (total === 0) return '';
  const allViolations = KNOWN_SEVERITIES.flatMap((sev) => bySeverity[sev] || []);
  return _buildPlanLines(
    evalData.dimension || 'dimension', total, bySeverity, allViolations,
    { principleKey: '_principle', reasonKey: '_findings' },
  );
}

export function buildDimensionPlanFromViolations(dimName, violations) {
  if (!violations || violations.length === 0) return '';
  const bySeverity = {};
  violations.forEach((v) => {
    const sev = normalizeSeverity(v.severity);
    if (!bySeverity[sev]) bySeverity[sev] = [];
    bySeverity[sev].push(v);
  });
  return _buildPlanLines(
    dimName, violations.length, bySeverity, violations,
    { principleKey: 'principle', reasonKey: 'reason' },
  );
}

// ---------------------------------------------------------------------------
// Shared group plan builder (used by PrincipleDetailPage, EvalPrincipleDetailPage, FileDetailPage)
// ---------------------------------------------------------------------------

/**
 * Build a markdown fix-plan for a group of violations (principle or file).
 *
 * @param {object} opts
 * @param {string}   opts.title              — plan heading, e.g. principle name or file path
 * @param {object[]} opts.violations         — flat list of violations
 * @param {object}   opts.violationsBySeverity — { critical: [], major: [], ... }
 * @param {string}   [opts.context]          — optional extra context line (e.g. findings)
 * @param {function} [opts.renderEntry]      — optional per-violation line renderer; defaults to shared template
 * @returns {string} markdown plan text
 */
export function buildGroupPlanText({ title, violations, violationsBySeverity, context, renderEntry }) {
  const totalViolations = violations.length;
  const lines = [
    ...GROUP_PLAN_PREAMBLE,
    '',
    `# Fix Plan: ${title}`,
    '',
    `**Total violations:** ${totalViolations}`,
  ];
  if (context) lines.push('', `**Context:** ${context}`);
  lines.push('', '---', '');

  const defaultRenderEntry = (v, i) => {
    const loc = v.file ? `${v.file}${v.line ? `:${v.line}` : ''}` : '';
    const entryLines = [];
    const heading = v._entryTitle
      ? `### ${i + 1}. ${v._entryTitle}${loc ? ` — \`${loc}\`` : ''}`
      : `### ${i + 1}.${loc ? ` \`${loc}\`` : ''}`;
    entryLines.push(heading);
    if (v.reason) entryLines.push('', `**Why it's a violation:** ${v.reason}`);
    const hint = getFixHint(v.req);
    if (hint) entryLines.push('', `**Expected fix:** ${hint}`);
    const linkedRefs = (v.reqRefs || []).filter(r => r.url && /^https?:\/\//.test(r.url));
    if (linkedRefs.length > 0) entryLines.push('', `**References:** ${linkedRefs.map(r => `${r.label} (${r.url})`).join(', ')}`);
    if (v.snippet) {
      entryLines.push('', '**Affected code:**');
      entryLines.push('```');
      capSnippet(v.snippet).split('\n').forEach((l) => entryLines.push(l));
      entryLines.push('```');
    }
    entryLines.push('');
    return entryLines;
  };

  const render = renderEntry || defaultRenderEntry;

  SEVERITY_ORDER.forEach((sev) => {
    const vs = violationsBySeverity[sev];
    if (!vs || vs.length === 0) return;
    lines.push(`## ${sev.charAt(0).toUpperCase() + sev.slice(1)} violations (${vs.length})`);
    lines.push('');
    vs.forEach((v, i) => lines.push(...render(v, i)));
  });

  lines.push(...GROUP_PLAN_OUTPUT);
  lines.push(PLAN_TEST_INSTRUCTION_GROUP);
  lines.push('', PLAN_COMPLETION_CHECKLIST);
  return lines.join('\n').trim();
}

// ---------------------------------------------------------------------------
// Shared single-violation plan builder
// ---------------------------------------------------------------------------

/**
 * Build a markdown fix-plan for a single violation.
 *
 * @param {object}   v          — the violation object
 * @param {string}   title      — heading title (e.g. principle name or dimension/principle combo)
 * @param {object}   [opts]     — optional extras
 * @param {object[]} [opts.reqRefs]   — reqRefs array for references line
 * @param {string}   [opts.reqFallback] — fallback requirement label when no refs
 * @returns {string} markdown plan text
 */
export function buildSingleViolationPlanText(v, title, opts = {}) {
  const loc = v.file ? `${v.file}${v.line ? `:${v.line}` : ''}` : '';
  const lines = [
    `# Fix Request: ${title}`,
    '',
    `**Severity:** ${v.severity || 'unknown'}`,
  ];
  if (loc) lines.push(`**File:** ${loc}`);
  if (v.snippet) lines.push('', '## Affected Code', '```', capSnippet(v.snippet), '```');
  if (v.reason) lines.push('', "## Why It's a Violation", v.reason);
  const hint = getFixHint(v.req);
  if (hint) lines.push('', `**Expected fix:** ${hint}`);
  const refs = opts.reqRefs || v.reqRefs;
  if (refs?.length > 0) {
    lines.push('', `**References:** ${refs.map(r => `${r.label} (${r.url})`).join(', ')}`);
  } else if (opts.reqFallback) {
    lines.push('', `**Requirement:** ${opts.reqFallback}`);
  }
  lines.push('', '---', 'Please provide a concrete, step-by-step fix for this specific violation.');
  if (loc) lines.push(`Apply it to \`${loc}\`.`);
  lines.push(PLAN_TEST_INSTRUCTION_SINGLE);
  return lines.join('\n').trim();
}
