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
import { KNOWN_SEVERITIES } from './constants.js';

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
    confidence: typeof entry.confidence === 'number' ? entry.confidence : 100,
    provenanceDowngrade: entry.provenanceDowngrade ?? false,
    ...(entry.cwe ? { cwe: entry.cwe } : {}),
  });

  if (dimension.dimension) current.dimensions.add(dimension.dimension);
  if (entry.principle) current.principles.add(entry.principle);

  bucket.set(file, current);
}

const DEFAULT_TOP_FILES_LIMIT = 500;

export function buildTopOffendingFiles(dimensions = [], filters = {}, limit = DEFAULT_TOP_FILES_LIMIT) {
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

/**
 * Build a synthetic "project root" file object from the same dimensions
 * structure that powers buildTopOffendingFiles. The result has the same
 * shape FileDetailPage expects (violationsBySeverity / compliance / counts),
 * so the project itself can be navigated to as if it were a file.
 */
export function buildProjectRootFile(dimensions = [], projectName = 'project') {
  const violationsBySeverity = { critical: [], major: [], minor: [], unknown: [] };
  const compliance = [];
  const dims = new Set();
  const principles = new Set();
  let total = 0;

  for (const dim of dimensions) {
    const dimName = dim.dimension || '';
    for (const v of dim.violations || []) {
      const sev = normalizeSeverity(v.severity);
      const enriched = { ...v, dimension: v.dimension || dimName };
      (violationsBySeverity[sev] || violationsBySeverity.unknown).push(enriched);
      total += 1;
      if (enriched.dimension) dims.add(enriched.dimension);
      if (enriched.principle) principles.add(enriched.principle);
    }
    for (const c of dim.compliance || []) {
      compliance.push({ ...c, dimension: c.dimension || dimName });
      if (dimName) dims.add(dimName);
      if (c.principle) principles.add(c.principle);
    }
  }

  return {
    file: projectName || 'project',
    total,
    critical: violationsBySeverity.critical.length,
    major: violationsBySeverity.major.length,
    minor: violationsBySeverity.minor.length,
    unknown: violationsBySeverity.unknown.length,
    dimensions: Array.from(dims).sort((a, b) => a.localeCompare(b)),
    dimensionsCount: dims.size,
    principlesCount: principles.size,
    violationsBySeverity,
    compliance,
  };
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
