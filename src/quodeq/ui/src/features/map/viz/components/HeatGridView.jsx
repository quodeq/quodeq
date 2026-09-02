import { useMemo, useState } from 'react';
import HeatGridCells from '../../../../components/HeatGridCells.jsx';
import { ICON_FOLDER } from '../../../../constants/navigation.jsx';
import { t } from '../../../../strings/index.js';

const COL_NAME = 'name';
const COL_CRITICAL = 'critical';
const COL_MAJOR = 'major';
const COL_MINOR = 'minor';
const COL_VIOLATIONS = 'violations';
const COL_HEALTH = 'health';

const COLUMNS = [
  { id: COL_NAME, label: t('map.colFileFolder'), align: 'left' },
  { id: COL_CRITICAL, label: 'Critical' },
  { id: COL_MAJOR, label: 'Major' },
  { id: COL_MINOR, label: 'Minor' },
  { id: COL_VIOLATIONS, label: 'Violations' },
  { id: COL_HEALTH, label: 'Health' },
];

function sortRows(items, sortCol, sortDir) {
  return [...items].sort((a, b) => {
    let va, vb;
    switch (sortCol) {
      case COL_NAME: va = a.name || ''; vb = b.name || ''; return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
      case COL_CRITICAL: va = a.severity.critical; vb = b.severity.critical; break;
      case COL_MAJOR: va = a.severity.major; vb = b.severity.major; break;
      case COL_MINOR: va = a.severity.minor; vb = b.severity.minor; break;
      case COL_VIOLATIONS: va = a.violations; vb = b.violations; break;
      case COL_HEALTH: va = a.complianceRate; vb = b.complianceRate; break;
      default: return 0;
    }
    const diff = sortDir === 'asc' ? va - vb : vb - va;
    return diff !== 0 ? diff : (a.name || '').localeCompare(b.name || '');
  });
}

/** Sort state + the sorted, violation/compliance-filtered rows for one node. */
function useHeatGridSort(node) {
  const [sortCol, setSortCol] = useState(COL_VIOLATIONS);
  const [sortDir, setSortDir] = useState('desc');

  const rows = useMemo(() => {
    const items = node.children.length > 0 ? node.children : [node];
    const filtered = items.filter((r) => r.violations > 0 || r.compliance > 0);
    return sortRows(filtered, sortCol, sortDir);
  }, [node, sortCol, sortDir]);

  const handleSort = (col) => {
    if (sortCol === col) {
      setSortDir((d) => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortCol(col);
      setSortDir(col === COL_NAME ? 'asc' : 'desc');
    }
  };

  return { rows, sortCol, sortDir, handleSort };
}

function HeatGridHeaderRow({ sortCol, sortDir, onSort }) {
  return (
    <tr>
      {COLUMNS.map((col) => (
        <th
          key={col.id}
          className={`heat-grid-th-sort viz-focusable${col.align === 'left' ? ' left' : ''}`}
          onClick={() => onSort(col.id)}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSort(col.id); } }}
          tabIndex={0}
          aria-sort={sortCol === col.id ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
        >
          {col.label}{sortCol === col.id ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
        </th>
      ))}
    </tr>
  );
}

function HeatGridRow({ row, onDrillDown, onFileClick, onCellClick, variant }) {
  const canDrill = !row.isFile && row.children?.length > 0;
  return (
    <tr>
      <td>
        <div
          className={`heat-grid-file${canDrill || row.isFile ? ' clickable viz-focusable' : ''}`}
          role={canDrill || row.isFile ? 'button' : undefined}
          tabIndex={canDrill || row.isFile ? 0 : undefined}
          onClick={() => canDrill ? onDrillDown(row.path) : row.isFile && onFileClick?.(row)}
          onKeyDown={(e) => e.key === 'Enter' && (canDrill ? onDrillDown(row.path) : row.isFile && onFileClick?.(row))}
          title={row.path}
        >
          {row.isFile ? null : <span className="heat-grid-folder-icon" aria-hidden="true">{ICON_FOLDER}</span>}
          {row.name}
        </div>
      </td>
      <HeatGridCells row={row} onCellClick={onCellClick} variant={variant} />
    </tr>
  );
}

export default function HeatGridView({ node, onDrillDown, onFileClick, onCellClick, variant = 'heat' }) {
  const { rows, sortCol, sortDir, handleSort } = useHeatGridSort(node);

  if (rows.length === 0) {
    return <p className="empty-state">{t('map.noData')}</p>;
  }

  const flat = variant === 'flat';
  const wrapCls = `heat-grid-wrap${flat ? ' heat-grid-wrap--flat' : ''}`;
  const tableCls = `heat-grid${flat ? ' heat-grid--flat' : ''}`;

  return (
    <div className={wrapCls}>
      <table className={tableCls}>
        <thead>
          <HeatGridHeaderRow sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
        </thead>
        <tbody>
          {rows.map((row) => (
            <HeatGridRow
              key={row.path}
              row={row}
              onDrillDown={onDrillDown}
              onFileClick={onFileClick}
              onCellClick={onCellClick}
              variant={variant}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}
