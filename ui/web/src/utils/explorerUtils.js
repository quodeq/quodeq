const KNOWN_SEVERITIES = ['critical', 'major', 'minor', 'unknown'];

export const PLAN_TEST_INSTRUCTION_GROUP =
  'After applying all fixes, run the test suite. If tests fail, fix the implementation first. Only update a test if it was explicitly written to assert the violation you just fixed — and explain your reasoning before modifying it.';

export const PLAN_TEST_INSTRUCTION_SINGLE =
  'After applying this fix, run the test suite. If tests fail, fix the implementation first. Only update a test if it was explicitly written to assert this specific violation — and explain your reasoning before modifying it.';

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

export function buildDimensionPlanText(evalData) {
  const SEVERITY_ORDER = ['critical', 'major', 'minor', 'unknown'];

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

  const dimName = evalData.dimension || 'dimension';
  const lines = [
    'You are a senior software engineer performing a targeted code review.',
    'Apply minimal, surgical fixes — no refactoring, no style changes beyond what is required.',
    '',
    `# Fix Plan: ${dimName} dimension`,
    '',
    `**Total violations:** ${total}`,
    '',
    '---',
    '',
  ];

  SEVERITY_ORDER.forEach((sev) => {
    const vs = bySeverity[sev];
    if (!vs || vs.length === 0) return;
    lines.push(`## ${sev.charAt(0).toUpperCase() + sev.slice(1)} violations (${vs.length})`);
    lines.push('');
    vs.forEach((v, i) => {
      const loc = v.file ? ` — \`${v.file}${v.line ? `:${v.line}` : ''}\`` : '';
      lines.push(`### ${i + 1}. ${v._principle || 'Violation'}${loc}`);
      if (v._findings) lines.push('', `**Why it's a violation:** ${v._findings}`);
      const snippet = v.code || v.snippet;
      if (snippet) {
        lines.push('', '**Affected code:**');
        lines.push('```');
        snippet.split('\n').forEach((l) => lines.push(l));
        lines.push('```');
      }
      lines.push('');
    });
  });

  lines.push('---');
  lines.push('');
  lines.push('For each violation above, provide a concrete, step-by-step fix.');
  lines.push(
    'Return each fix as an exact replacement block or unified diff. No explanations beyond what is needed to apply the fix.'
  );
  lines.push(PLAN_TEST_INSTRUCTION_GROUP);

  return lines.join('\n').trim();
}

export function buildDimensionPlanFromViolations(dimName, violations) {
  if (!violations || violations.length === 0) return '';

  const SEVERITY_ORDER = ['critical', 'major', 'minor', 'unknown'];
  const bySeverity = {};

  violations.forEach((v) => {
    const sev = normalizeSeverity(v.severity);
    if (!bySeverity[sev]) bySeverity[sev] = [];
    bySeverity[sev].push(v);
  });

  const lines = [
    'You are a senior software engineer performing a targeted code review.',
    'Apply minimal, surgical fixes — no refactoring, no style changes beyond what is required.',
    '',
    `# Fix Plan: ${dimName} dimension`,
    '',
    `**Total violations:** ${violations.length}`,
    '',
    '---',
    '',
  ];

  SEVERITY_ORDER.forEach((sev) => {
    const vs = bySeverity[sev];
    if (!vs || vs.length === 0) return;
    lines.push(`## ${sev.charAt(0).toUpperCase() + sev.slice(1)} violations (${vs.length})`);
    lines.push('');
    vs.forEach((v, i) => {
      const loc = v.file ? ` — \`${v.file}${v.line ? `:${v.line}` : ''}\`` : '';
      lines.push(`### ${i + 1}. ${v.principle || 'Violation'}${loc}`);
      if (v.reason) lines.push('', `**Why it's a violation:** ${v.reason}`);
      const snippet = v.code || v.snippet;
      if (snippet) {
        lines.push('', '**Affected code:**');
        lines.push('```');
        snippet.split('\n').forEach((l) => lines.push(l));
        lines.push('```');
      }
      lines.push('');
    });
  });

  lines.push('---');
  lines.push('');
  lines.push('For each violation above, provide a concrete, step-by-step fix.');
  lines.push(
    'Return each fix as an exact replacement block or unified diff. No explanations beyond what is needed to apply the fix.'
  );
  lines.push(PLAN_TEST_INSTRUCTION_GROUP);

  return lines.join('\n').trim();
}
