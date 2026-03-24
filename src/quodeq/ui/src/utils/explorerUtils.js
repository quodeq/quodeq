// Re-export plan constants and builders so existing imports keep working.
export {
  PLAN_TEST_INSTRUCTION_GROUP,
  PLAN_TEST_INSTRUCTION_SINGLE,
  PLAN_COMPLETION_CHECKLIST,
  FIX_HINTS,
  getFixHint,
  buildDimensionPlanText,
  buildDimensionPlanFromViolations,
  buildGroupPlanText,
  buildSingleViolationPlanText,
} from './planBuilder.js';

const KNOWN_SEVERITIES = ['critical', 'major', 'minor', 'unknown'];

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

function aggregateViolationEntry(bucket, dimension, entry) {
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

  if (dimension.dimension) current.dimensions.add(dimension.dimension);
  if (entry.principle) current.principles.add(entry.principle);

  bucket.set(file, current);
}

export function buildTopOffendingFiles(dimensions = [], filters = {}, limit = Infinity) {
  const bucket = new Map();

  dimensions.forEach((dimension) => {
    (dimension.violations || []).forEach((entry) => {
      if (!matchesViolationFilters(entry, filters)) return;
      if (!entry.file) return;
      aggregateViolationEntry(bucket, dimension, entry);
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
