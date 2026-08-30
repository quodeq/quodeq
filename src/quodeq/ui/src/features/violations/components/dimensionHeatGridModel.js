/**
 * Pure row-building for the flat dimension/principle heat grid. Nothing
 * here touches i18n or the DOM (COLUMNS calls t() at module scope, so it —
 * and PRINCIPLE_INDENT_PX — stay in DimensionHeatGridView.jsx).
 */

export const DEFAULT_SEVERITY = 'minor';

export function getSortValue(row, col) {
  switch (col) {
    case 'name': return row.name || '';
    case 'critical': return row.severity.critical;
    case 'major': return row.severity.major;
    case 'minor': return row.severity.minor;
    case 'violations': return row.violations;
    case 'health': return row.complianceRate;
    default: return 0;
  }
}

export function comparator(col, dir) {
  return (a, b) => {
    const va = getSortValue(a, col);
    const vb = getSortValue(b, col);
    if (col === 'name') {
      return dir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
    }
    const diff = dir === 'asc' ? va - vb : vb - va;
    return diff !== 0 ? diff : (a.name || '').localeCompare(b.name || '');
  };
}

export function newPrincipleEntry() {
  return { violations: 0, compliance: 0, severity: { critical: 0, major: 0, minor: 0 }, violationItems: [], complianceItems: [] };
}

export function buildPrincipleRow(name, data, dim) {
  const total = data.violations + data.compliance;
  return {
    type: 'principle',
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

  const dimSev = { critical: 0, major: 0, minor: 0 };
  const principleMap = new Map();

  for (const v of violations) {
    const sev = (v.severity || DEFAULT_SEVERITY).toLowerCase();
    if (dimSev[sev] !== undefined) dimSev[sev]++;
    const pName = v.principle || '(unknown)';
    if (!principleMap.has(pName)) principleMap.set(pName, newPrincipleEntry());
    const p = principleMap.get(pName);
    p.violations++;
    if (p.severity[sev] !== undefined) p.severity[sev]++;
    p.violationItems.push(v);
  }

  for (const c of compliance) {
    const pName = c.principle || '(unknown)';
    if (!principleMap.has(pName)) principleMap.set(pName, newPrincipleEntry());
    principleMap.get(pName).compliance++;
    principleMap.get(pName).complianceItems.push(c);
  }

  const dimTotal = violations.length + compliance.length;
  const dimRow = {
    type: 'dimension', name: dim.dimension, violations: violations.length,
    compliance: compliance.length, severity: dimSev,
    complianceRate: dimTotal > 0 ? compliance.length / dimTotal : 0, raw: dim,
  };

  const principles = Array.from(principleMap.entries())
    .map(([name, data]) => buildPrincipleRow(name, data, dim));

  return { dimRow, principles };
}

/**
 * Flatten dimension groups into sorted rows. Non-mutating: sorts a COPY of
 * `groups` ([...groups].sort) rather than the array the caller passed in
 * (the original sorted `groups` — and each group's `principles` array — in
 * place; changed here for `groups` only, kept for `principles` since each
 * group object is freshly built per call and not retained by any caller).
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
