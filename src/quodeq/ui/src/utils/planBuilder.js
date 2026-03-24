import { SEVERITY_ORDER } from './formatters.js';

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

export const FIX_HINTS = {
  // Maintainability
  'M-ANA-1': 'Split file or extract code to a new module to reduce line count below 300',
  'M-ANA-2': 'Extract a helper function to bring the function under 50 lines',
  'M-ANA':   'Improve code clarity — reduce nesting, add structure, simplify control flow',
  'M-MOD-1': 'Reduce callees by extracting a helper that groups related calls',
  'M-MOD-4': 'Group related parameters into an object or dataclass (max 5)',
  'M-MOD-5': 'Extract into a configurable constant or injectable function',
  'M-MOD':   'Reduce coupling — extract dependency, use injection, or narrow the interface',
  'M-REU-1': 'Extract duplicated code into a shared function or hook',
  'M-REU-2': 'Add an injectable parameter so the default can be overridden for testing',
  'M-REU':   'Make the code reusable — extract shared logic or add injection points',
  'M-MDF-1': 'Replace the hard-coded literal with a named constant',
  'M-MDF':   'Make the code easier to modify — extract constants, reduce coupling',
  'M-TST':   'Improve testability — add injection points, reduce hidden dependencies',
  // Reliability
  'R-MAT':   'Add error handling, input validation, or defensive checks',
  'R-FT':    'Add fault tolerance — retry logic, fallback, or graceful degradation',
  'R-REC':   'Add recovery mechanism — cleanup, state restoration, or rollback',
  'R-AVL':   'Improve availability — reduce single points of failure',
  // Security
  'S-CON':   'Fix confidentiality issue — sanitize output, restrict access, encrypt data',
  'S-INT':   'Fix integrity issue — validate input, use parameterized queries, check boundaries',
  'S-AUT':   'Fix authentication issue — strengthen auth checks, secure token handling',
  'S-ACC':   'Fix accountability issue — add logging, audit trail, or access tracking',
  'S-NRP':   'Fix non-repudiation — add tamper-evident logging or signing',
  // Performance
  'P-TIM':   'Optimize time behavior — reduce unnecessary computation, cache, or batch',
  'P-RES':   'Reduce resource usage — close handles, limit allocations, pool connections',
  'P-CAP':   'Improve capacity — add pagination, streaming, or bounded data structures',
  // Flexibility
  'F-ADP':   'Improve adaptability — make configurable, use abstraction, externalize settings',
  'F-SCL':   'Improve scalability — avoid bottlenecks, support horizontal growth',
  'F-INS':   'Improve installability — simplify setup, reduce hard-coded paths',
  'F-RPL':   'Improve replaceability — use interfaces, reduce tight coupling',
  // Usability
  'U-APR':   'Improve recognizability — add labels, descriptions, or help text',
  'U-LRN':   'Improve learnability — add examples, defaults, or progressive disclosure',
  'U-OPR':   'Improve operability — simplify controls, reduce steps, add feedback',
  'U-UEP':   'Add user error protection — validate input, confirm destructive actions',
  'U-UIA':   'Improve aesthetics — fix layout, spacing, or visual consistency',
  'U-ACC':   'Improve accessibility — add ARIA labels, keyboard nav, or contrast',
};

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

const PLAN_SYSTEM_PREAMBLE = [
  'You are a senior software engineer resolving verified code-quality violations.',
  '',
  '## Operating Rules',
  '',
  '1. **Read before writing.** Before modifying any file, read it in full. Never guess at contents.',
  '2. **Scope.** Fix only the listed violations. Do not rename, restyle, or refactor anything else.',
  '3. **Structural changes are allowed when required.** Some violations (e.g., "file too long", "duplicated code") explicitly require splitting files, extracting helpers, or moving data to config. Apply those changes — but go no further than what the violation describes.',
  '4. **Dependency order.** When one fix creates infrastructure another fix depends on (shared helpers, centralized config), complete the foundational fix first.',
  '5. **Test after each logical group.** Run the project\'s test suite after every cluster of related changes. Fix breakage immediately before proceeding.',
  '6. **Verify each fix.** After applying a fix, confirm it resolves the violation (e.g., re-count lines, re-check nesting depth, grep for the removed pattern).',
  '7. **Tests are not targets.** Only modify a test if it explicitly asserts the violated pattern you just changed. Explain your reasoning before touching any test.',
];

const PLAN_OUTPUT_INSTRUCTIONS = [
  '---', '', '## How to apply these fixes', '',
  '**For each violation above:**',
  '1. Read the affected file(s) in full.',
  '2. Identify the minimal change that resolves the stated violation.',
  '3. Apply the fix as an exact replacement block (showing before \u2192 after) or a unified diff.',
  '4. State a one-line verification step (e.g., `wc -l file.py` should be \u2264 300, `grep -c "except Exception.*pass" file.py` should be 0).',
  '', '**Sequencing:** If multiple violations touch the same file or one fix creates infrastructure for another, group them and apply in dependency order \u2014 foundational changes first.', '',
];

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

const GROUP_PLAN_PREAMBLE = [
  'You are a senior software engineer performing a targeted code review.',
  'Apply minimal, surgical fixes — no refactoring, no style changes beyond what is required.',
];

const GROUP_PLAN_OUTPUT = [
  '---', '',
  'For each violation above, provide a concrete, step-by-step fix.',
  'Return each fix as an exact replacement block or unified diff. No explanations beyond what is needed to apply the fix.',
];

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
      v.snippet.split('\n').forEach((l) => entryLines.push(l));
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
  if (v.snippet) lines.push('', '## Affected Code', '```', v.snippet, '```');
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
