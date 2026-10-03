/**
 * Pure row-building for the flat dimension/principle heat grid. Nothing
 * here touches i18n or the DOM (COLUMNS calls t() at module scope, so it —
 * and PRINCIPLE_INDENT_PX — stay in DimensionHeatGridView.jsx).
 */
import { SEVERITY } from '../../../vocab/severity.js';
import { SORT_DIR } from '../../../vocab/sortDirection.js';
import { COL_NAME, COL_VIOLATIONS, COL_HEALTH } from '../../../components/heatGridColumns.js';
import { ROW_TYPE } from '../violationsVocab.js';
import { emptySeverityCounts } from '../../../utils/severity.js';

export const DEFAULT_SEVERITY = SEVERITY.MINOR;
const UNKNOWN_PRINCIPLE = '(unknown)'; // findings that name no principle share one synthetic row

export function getSortValue(row, col) {
  switch (col) {
    case COL_NAME: return row.name || '';
    case SEVERITY.CRITICAL: return row.severity.critical;
    case SEVERITY.MAJOR: return row.severity.major;
    case SEVERITY.MINOR: return row.severity.minor;
    case COL_VIOLATIONS: return row.violations;
    case COL_HEALTH: return row.complianceRate;
    default: return 0;
  }
}

export function comparator(col, dir) {
  return (a, b) => {
    const va = getSortValue(a, col);
    const vb = getSortValue(b, col);
    if (col === COL_NAME) {
      return dir === SORT_DIR.ASC ? va.localeCompare(vb) : vb.localeCompare(va);
    }
    const diff = dir === SORT_DIR.ASC ? va - vb : vb - va;
    return diff !== 0 ? diff : (a.name || '').localeCompare(b.name || '');
  };
}

export function newPrincipleEntry() {
  return { violations: 0, compliance: 0, severity: emptySeverityCounts(), violationItems: [], complianceItems: [] };
}

// The principle's entry in `principleMap`, created on first sight.
function principleEntry(principleMap, name) {
  let entry = principleMap.get(name);
  if (!entry) {
    entry = newPrincipleEntry();
    principleMap.set(name, entry);
  }
  return entry;
}

export function buildPrincipleRow(name, data, dim) {
  const total = data.violations + data.compliance;
  return {
    type: ROW_TYPE.PRINCIPLE,
    name,
    violations: data.violations,
    compliance: data.compliance,
    severity: data.severity,
    complianceRate: total > 0 ? data.compliance / total : 0,
    dimension: dim.dimension,
    raw: dim,
    principleObj: {
      principle: name, dimension: dim.dimension, total: data.violations,
      critical: data.severity.critical, major: data.severity.major, minor: data.severity.minor,
      violations: data.violationItems, compliance: data.complianceItems,
    },
  };
}

export function buildDimensionGroup(dim) {
  const violations = dim.violations || [];
  const compliance = dim.compliance || [];
  if (violations.length === 0 && compliance.length === 0) return null;

  const dimSev = emptySeverityCounts();
  const principleMap = new Map();

  for (const v of violations) {
    const sev = (v.severity || DEFAULT_SEVERITY).toLowerCase();
    if (dimSev[sev] !== undefined) dimSev[sev]++;
    const p = principleEntry(principleMap, v.principle || UNKNOWN_PRINCIPLE);
    p.violations++;
    if (p.severity[sev] !== undefined) p.severity[sev]++;
    p.violationItems.push(v);
  }

  for (const c of compliance) {
    const p = principleEntry(principleMap, c.principle || UNKNOWN_PRINCIPLE);
    p.compliance++;
    p.complianceItems.push(c);
  }

  const dimTotal = violations.length + compliance.length;
  const dimRow = {
    type: ROW_TYPE.DIMENSION, name: dim.dimension, violations: violations.length,
    compliance: compliance.length, severity: dimSev,
    complianceRate: dimTotal > 0 ? compliance.length / dimTotal : 0, raw: dim,
  };

  const principles = Array.from(principleMap.entries())
    .map(([name, data]) => buildPrincipleRow(name, data, dim));

  return { dimRow, principles };
}

/**
 * Flatten dimension groups into sorted rows. Sorts a COPY of `groups`
 * ([...groups].sort), never the caller's array. Each group's `principles`
 * array is sorted in place: group objects are built fresh per call and no
 * caller retains them.
 */
export function flattenAndSort(groups, sortCol, sortDir) {
  const cmp = comparator(sortCol, sortDir);
  const sortedGroups = [...groups].sort((a, b) => cmp(a.dimRow, b.dimRow));
  const rows = [];
  for (const g of sortedGroups) {
    rows.push(g.dimRow);
    g.principles.sort(cmp);
    rows.push(...g.principles);
  }
  return rows;
}

export function buildRows(dimensions, sortCol, sortDir) {
  const groups = dimensions.map(buildDimensionGroup).filter(Boolean);
  return flattenAndSort(groups, sortCol, sortDir);
}
