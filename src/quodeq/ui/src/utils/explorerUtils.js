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

/**
 * Whether an entry survives the principle and file-substring filters. An
 * empty filter matches everything.
 */
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

/**
 * matchesEntryFilters plus the severity filter, for violations rather than
 * compliance entries.
 */
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
    scopeDowngrade: entry.scopeDowngrade ?? null,
    ...(entry.cwe ? { cwe: entry.cwe } : {}),
  });

  if (dimension.dimension) current.dimensions.add(dimension.dimension);
  if (entry.principle) current.principles.add(entry.principle);

  bucket.set(file, current);
}

const DEFAULT_TOP_FILES_LIMIT = 500;

/**
 * Rolls the filtered violations across every dimension up per file, ordered
 * worst first and capped at `limit` rows.
 *
 * This is the model behind the "top offending files" tables.
 */
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

/** Folds one dimension's violations into the project-root accumulators. */
function collectRootViolations(dim, acc) {
  const dimName = dim.dimension || '';
  for (const v of dim.violations || []) {
    const sev = normalizeSeverity(v.severity);
    const enriched = { ...v, dimension: v.dimension || dimName };
    (acc.violationsBySeverity[sev] || acc.violationsBySeverity.unknown).push(enriched);
    acc.total += 1;
    if (enriched.dimension) acc.dims.add(enriched.dimension);
    if (enriched.principle) acc.principles.add(enriched.principle);
  }
}

/** Folds one dimension's compliance entries into the same accumulators. */
function collectRootCompliance(dim, acc) {
  const dimName = dim.dimension || '';
  for (const c of dim.compliance || []) {
    acc.compliance.push({ ...c, dimension: c.dimension || dimName });
    if (dimName) acc.dims.add(dimName);
    if (c.principle) acc.principles.add(c.principle);
  }
}

/**
 * Build a synthetic "project root" file object from the same dimensions
 * structure that powers buildTopOffendingFiles. The result has the same
 * shape FileDetailPage expects (violationsBySeverity / compliance / counts),
 * so the project itself can be navigated to as if it were a file.
 */
export function buildProjectRootFile(dimensions = [], projectName = 'project') {
  const acc = {
    violationsBySeverity: { critical: [], major: [], minor: [], unknown: [] },
    compliance: [],
    dims: new Set(),
    principles: new Set(),
    total: 0,
  };

  for (const dim of dimensions) {
    collectRootViolations(dim, acc);
    collectRootCompliance(dim, acc);
  }

  const { violationsBySeverity, compliance, dims, principles } = acc;
  return {
    file: projectName || 'project',
    total: acc.total,
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

/**
 * Keeps the current selection when it still exists, otherwise falls back to
 * the first project (or an empty string when there are none), so a deleted or
 * renamed project can never leave the UI pointing at nothing.
 */
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
