import { useMemo, useState } from 'react';
import HeatGridCells, { HEAT_GRID_VARIANT, makeColumnSortHandler } from '../../../components/HeatGridCells.jsx';
import { COL_NAME, COL_VIOLATIONS, COL_HEALTH, COL_ALIGN_LEFT } from '../../../components/heatGridColumns.js';
import { buildRows } from './dimensionHeatGridModel.js';
import { ROW_TYPE } from '../violationsVocab.js';
import { activateOnKey } from '../../../utils/a11y.js';
import { t } from '../../../strings/index.js';
import { SORT_DIR } from '../../../vocab/sortDirection.js';

const PRINCIPLE_INDENT_PX = 24;

function ariaSort(isActive, sortDir) {
  if (!isActive) return 'none';
  return sortDir === SORT_DIR.ASC ? 'ascending' : 'descending';
}

const COLUMNS = [
  { id: COL_NAME, label: t('violations.colDimensionPrinciple'), align: COL_ALIGN_LEFT },
  { id: 'critical', label: t('violations.colCritical') },
  { id: 'major', label: t('violations.colMajor') },
  { id: 'minor', label: t('violations.colMinor') },
  { id: COL_VIOLATIONS, label: t('violations.colViolations') },
  { id: COL_HEALTH, label: t('violations.colHealth') },
];

function HeatGridHead({ sortCol, sortDir, handleSort }) {
  return (
    <thead>
      <tr>
        {COLUMNS.map((col) => (
          <th
            key={col.id}
            className={`heat-grid-th-sort${col.align === COL_ALIGN_LEFT ? ' left' : ''}`}
            aria-sort={ariaSort(sortCol === col.id, sortDir)}
          >
            {/* A real <button> so sorting is reachable from the keyboard (a <th>
                is not focusable). It fills the cell and looks like plain header
                text: see `.heat-grid-th-sort > button` in styles/map.css. */}
            <button
              type="button"
              aria-label={t('violations.sortByAria', { column: col.label })}
              onClick={() => handleSort(col.id)}
            >
              {col.label}{sortCol === col.id ? (sortDir === SORT_DIR.ASC ? ' ↑' : ' ↓') : ''}
            </button>
          </th>
        ))}
      </tr>
    </thead>
  );
}

function HeatGridRow({ row, onDimensionClick, onPrincipleClick, onCellClick }) {
  const isDim = row.type === ROW_TYPE.DIMENSION;
  return (
    <tr className={isDim ? 'heat-grid-dim-row' : undefined}>
      <td>
        <div
          className="heat-grid-file clickable"
          role="button"
          tabIndex={0}
          onClick={() => isDim ? onDimensionClick?.(row.raw) : onPrincipleClick?.(row.principleObj)}
          onKeyDown={activateOnKey(() => isDim ? onDimensionClick?.(row.raw) : onPrincipleClick?.(row.principleObj))}
          style={isDim ? undefined : { paddingLeft: PRINCIPLE_INDENT_PX }}
        >
          {row.name}
        </div>
      </td>
      <HeatGridCells row={row} onCellClick={onCellClick} variant={HEAT_GRID_VARIANT.FLAT} />
    </tr>
  );
}

export default function DimensionHeatGridView({ dimensions, onDimensionClick, onPrincipleClick, onCellClick }) {
  const [sortCol, setSortCol] = useState(COL_VIOLATIONS);
  const [sortDir, setSortDir] = useState(SORT_DIR.DESC);

  const rows = useMemo(() => buildRows(dimensions, sortCol, sortDir), [dimensions, sortCol, sortDir]);

  const handleSort = makeColumnSortHandler({ sortCol, setSortCol, setSortDir, ascCol: COL_NAME });

  if (rows.length === 0) {
    return <p className="empty-state">{t('violations.noViolationsFound')}</p>;
  }

  return (
    <div className="heat-grid-wrap heat-grid-wrap--flat">
      <table className="heat-grid heat-grid--flat">
        <HeatGridHead sortCol={sortCol} sortDir={sortDir} handleSort={handleSort} />
        <tbody>
          {rows.map((row, i) => (
            <HeatGridRow key={`${row.type}-${row.name}-${i}`} row={row} onDimensionClick={onDimensionClick} onPrincipleClick={onPrincipleClick} onCellClick={onCellClick} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
