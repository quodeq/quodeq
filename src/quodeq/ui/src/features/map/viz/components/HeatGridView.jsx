import { useMemo, useState } from 'react';
import HeatGridCells from './HeatGridCells.jsx';

const COLUMNS = [
  { id: 'name', label: 'File / Folder', align: 'left' },
  { id: 'critical', label: 'Critical' },
  { id: 'major', label: 'Major' },
  { id: 'minor', label: 'Minor' },
  { id: 'violations', label: 'Violations' },
  { id: 'health', label: 'Health' },
];

function sortRows(items, sortCol, sortDir) {
  return [...items].sort((a, b) => {
    let va, vb;
    switch (sortCol) {
      case 'name': va = a.name || ''; vb = b.name || ''; return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
      case 'critical': va = a.severity.critical; vb = b.severity.critical; break;
      case 'major': va = a.severity.major; vb = b.severity.major; break;
      case 'minor': va = a.severity.minor; vb = b.severity.minor; break;
      case 'violations': va = a.violations; vb = b.violations; break;
      case 'health': va = a.complianceRate; vb = b.complianceRate; break;
      default: return 0;
    }
    const diff = sortDir === 'asc' ? va - vb : vb - va;
    return diff !== 0 ? diff : (a.name || '').localeCompare(b.name || '');
  });
}

export default function HeatGridView({ node, onDrillDown, onFileClick, onCellClick }) {
  const [sortCol, setSortCol] = useState('violations');
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
      setSortDir(col === 'name' ? 'asc' : 'desc');
    }
  };

  if (rows.length === 0) {
    return <p className="empty-state">No data available for this view.</p>;
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
          {rows.map((row) => {
            const canDrill = !row.isFile && row.children?.length > 0;
            return (
              <tr key={row.path}>
                <td>
                  <div
                    className={`heat-grid-file${canDrill || row.isFile ? ' clickable' : ''}`}
                    role={canDrill || row.isFile ? 'button' : undefined}
                    tabIndex={canDrill || row.isFile ? 0 : undefined}
                    onClick={() => canDrill ? onDrillDown(row.path) : row.isFile && onFileClick?.(row)}
                    onKeyDown={(e) => e.key === 'Enter' && (canDrill ? onDrillDown(row.path) : row.isFile && onFileClick?.(row))}
                    title={row.path}
                  >
                    {row.isFile ? '' : '\uD83D\uDCC1 '}{row.name}
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
