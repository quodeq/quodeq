const KNOWN_SEVERITIES = ['critical', 'major', 'minor', 'unknown'];

export const PLAN_TEST_INSTRUCTION_GROUP =
  'After completing each group of related fixes, run the full test suite (`npm test` / `pytest` / the project\'s test command). If tests fail, diagnose and fix the breakage before moving on. Only modify a test if it was explicitly asserting the exact pattern you just changed — state your reasoning before editing any test file.';

export const PLAN_TEST_INSTRUCTION_SINGLE =
  'After applying this fix, run the full test suite. If tests fail, diagnose and fix the breakage before moving on. Only modify a test if it was explicitly asserting the exact pattern you just changed — state your reasoning before editing any test file.';

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
  '3. Apply the fix as an exact replacement block (showing before → after) or a unified diff.',
  '4. State a one-line verification step (e.g., `wc -l file.py` should be ≤ 300, `grep -c "except Exception.*pass" file.py` should be 0).',
  '', '**Sequencing:** If multiple violations touch the same file or one fix creates infrastructure for another, group them and apply in dependency order — foundational changes first.', '',
];

function normalizeSeverity(value) {
  const normalized = String(value || 'unknown').toLowerCase();
  return KNOWN_SEVERITIES.includes(normalized) ? normalized : 'unknown';
}

export function matchesEntryFilters(entry, { selectedPrinciples = [], fileFilter = '' } = {}) {
  if (selectedPrinciples.length > 0 && !selectedPrinciples.includes(entry.principle || '')) {
    return false;
  }

  const normalizedFilter = fileFilter.trim().toLowerCase();
  if (normalizedFilter) {
    const fileValue = String(entry.file || '').toLowerCase();
    if (!fileValue.includes(normalizedFilter)) {
      return false;
    }
  }

  return true;
}

export function matchesViolationFilters(
  entry,
  { selectedSeverities = [], selectedPrinciples = [], fileFilter = '' } = {}
) {
  if (!matchesEntryFilters(entry, { selectedPrinciples, fileFilter })) {
    return false;
  }

  if (selectedSeverities.length > 0) {
    const severity = normalizeSeverity(entry.severity);
    if (!selectedSeverities.includes(severity)) {
      return false;
    }
  }

  return true;
}

export function buildTopOffendingFiles(dimensions = [], filters = {}, limit = Infinity) {
  const bucket = new Map();

  dimensions.forEach((dimension) => {
    (dimension.violations || []).forEach((entry) => {
      if (!matchesViolationFilters(entry, filters)) {
        return;
      }

      if (!entry.file) return;

      const file = entry.file;
      const severity = normalizeSeverity(entry.severity);

      const current = bucket.get(file) || {
        file,
        total: 0,
        critical: 0,
        major: 0,
        minor: 0,
        unknown: 0,
        dimensions: new Set(),
        principles: new Set(),
        violationsBySeverity: { critical: [], major: [], minor: [], unknown: [] },
      };

      current.total += 1;
      current[severity] += 1;
      current.violationsBySeverity[severity].push({
        dimension: dimension.dimension || '',
        principle: entry.principle || '',
        file: entry.file || '',
        line: entry.line || null,
        snippet: entry.snippet || '',
        title: entry.title || '',
        reason: entry.reason || '',
        severity,
        ...(entry.cwe ? { cwe: entry.cwe } : {}),
      });

      if (dimension.dimension) {
        current.dimensions.add(dimension.dimension);
      }
      if (entry.principle) {
        current.principles.add(entry.principle);
      }

      bucket.set(file, current);
    });
  });

  return Array.from(bucket.values())
    .map((item) => ({
      file: item.file,
      total: item.total,
      critical: item.critical,
      major: item.major,
      minor: item.minor,
      unknown: item.unknown,
      dimensions: Array.from(item.dimensions).sort((a, b) => a.localeCompare(b)),
      dimensionsCount: item.dimensions.size,
      principlesCount: item.principles.size,
      violationsBySeverity: item.violationsBySeverity,
    }))
    .sort((a, b) => {
      if (b.critical !== a.critical) return b.critical - a.critical;
      if (b.major !== a.major) return b.major - a.major;
      if (b.minor !== a.minor) return b.minor - a.minor;
      return b.total - a.total;
    })
    .slice(0, limit);
}

export function pickValidProject(projects = [], selectedProject = '') {
  if (!Array.isArray(projects) || projects.length === 0) {
    return '';
  }

  const names = projects.map((p) => p.name);
  if (selectedProject && names.includes(selectedProject)) {
    return selectedProject;
  }

  return names[0];
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
  return lines.join('\n').trim();
}

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
