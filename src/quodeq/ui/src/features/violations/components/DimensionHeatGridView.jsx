import { useMemo, useState } from 'react';
import HeatGridCells from '../../../components/HeatGridCells.jsx';
import { buildRows } from './dimensionHeatGridModel.js';
import { t } from '../../../strings/index.js';

const PRINCIPLE_INDENT_PX = 24;

const COLUMNS = [
  { id: 'name', label: t('violations.colDimensionPrinciple'), align: 'left' },
  { id: 'critical', label: t('violations.colCritical') },
  { id: 'major', label: t('violations.colMajor') },
  { id: 'minor', label: t('violations.colMinor') },
  { id: 'violations', label: t('violations.colViolations') },
  { id: 'health', label: t('violations.colHealth') },
];

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
    return <p className="empty-state">{t('violations.noViolationsFound')}</p>;
  }

  return (
    <div className="heat-grid-wrap heat-grid-wrap--flat">
      <table className="heat-grid heat-grid--flat">
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
                <HeatGridCells row={row} onCellClick={onCellClick} variant="flat" />
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
