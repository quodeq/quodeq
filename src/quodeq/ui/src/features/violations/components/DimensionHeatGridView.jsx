import { useMemo, useState } from 'react';
import HeatGridCells from '../../../components/HeatGridCells.jsx';

const DEFAULT_SEVERITY = 'minor';
const PRINCIPLE_INDENT_PX = 24;

const COLUMNS = [
  { id: 'name', label: 'Dimension / Principle', align: 'left' },
  { id: 'critical', label: 'Critical' },
  { id: 'major', label: 'Major' },
  { id: 'minor', label: 'Minor' },
  { id: 'violations', label: 'Violations' },
  { id: 'health', label: 'Health' },
];

function getSortValue(row, col) {
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

function comparator(col, dir) {
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

function newPrincipleEntry() {
  return { violations: 0, compliance: 0, severity: { critical: 0, major: 0, minor: 0 }, violationItems: [], complianceItems: [] };
}

function buildPrincipleRow(name, data, dim) {
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

function buildDimensionGroup(dim) {
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

function flattenAndSort(groups, sortCol, sortDir) {
  const cmp = comparator(sortCol, sortDir);
  groups.sort((a, b) => cmp(a.dimRow, b.dimRow));
  const rows = [];
  for (const g of groups) {
    rows.push(g.dimRow);
    g.principles.sort(cmp);
    rows.push(...g.principles);
  }
  return rows;
}

function buildRows(dimensions, sortCol, sortDir) {
  const groups = dimensions.map(buildDimensionGroup).filter(Boolean);
  return flattenAndSort(groups, sortCol, sortDir);
}

export default function DimensionHeatGridView({ dimensions, onDimensionClick, onPrincipleClick, onCellClick }) {
  const [sortCol, setSortCol] = useState('violations');
  const [sortDir, setSortDir] = useState('desc');

  const rows = useMemo(() => buildRows(dimensions, sortCol, sortDir), [dimensions, sortCol, sortDir]);

  const handleSort = (col) => {
    if (sortCol === col) {
      setSortDir((d) => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortCol(col);
      setSortDir(col === 'name' ? 'asc' : 'desc');
    }
  };

  if (rows.length === 0) {
    return <p className="empty-state">No violations found.</p>;
  }

  return (
    <div className="heat-grid-wrap">
      <table className="heat-grid">
        <thead>
          <tr>
            {COLUMNS.map((col) => (
              <th key={col.id} className={`heat-grid-th-sort${col.align === 'left' ? ' left' : ''}`} onClick={() => handleSort(col.id)}>
                {col.label}{sortCol === col.id ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const isDim = row.type === 'dimension';
            return (
              <tr key={`${row.type}-${row.name}-${i}`} className={isDim ? 'heat-grid-dim-row' : undefined}>
                <td>
                  <div
                    className="heat-grid-file clickable"
                    role="button"
                    tabIndex={0}
                    onClick={() => isDim ? onDimensionClick?.(row.raw) : onPrincipleClick?.(row.principleObj)}
                    onKeyDown={(e) => e.key === 'Enter' && (isDim ? onDimensionClick?.(row.raw) : onPrincipleClick?.(row.principleObj))}
                    style={isDim ? undefined : { paddingLeft: PRINCIPLE_INDENT_PX }}
                  >
                    {row.name}
                  </div>
                </td>
                <HeatGridCells row={row} onCellClick={onCellClick} />
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
