import { severityCellStyle, complianceRateCellStyle, severityColor, complianceRateColor } from '../features/map/viz/core/mapColors.js';
import { t } from '../strings/index.js';
import { PERCENT } from '../constants.js';
import { activateOnKey } from '../utils/a11y.js';
import { SEVERITY_ORDER } from '../vocab/severity.js';
import { SORT_DIR } from '../vocab/sortDirection.js';
import { pluralKey } from '../utils/plural.js';

// The catalog has no pluralisation, so a count of one takes its own key. An
// unnamed row gets its fallback from the catalog too, not a bare literal.
const rowLabel = (row) => row.name || t('heatGrid.unnamedRow');
const violationsAriaKey = (count) => pluralKey(count, 'heatGrid.violationsCellAriaOne', 'heatGrid.violationsCellAria');

/**
 * Renders the severity + violations + health cells for a heat grid row.
 *
 * Single shared component for both heat grids:
 *  - HeatGridView (Map page file tree) — default filled "heat" variant.
 *  - DimensionHeatGridView (Violations tab by-dimension/by-file tables) —
 *    pass `variant="flat"` for the leaner text-only treatment.
 *
 * Both grids share these cells so every clickable cell gets the same keyboard
 * activation, aria labels and `viz-focusable` focus ring; keep one copy
 * rather than forking it per grid.
 */
function SeverityCell({ row, sev, flat, onCellClick }) {
  const count = row.severity[sev];
  const hasValue = count > 0;
  const style = !hasValue
    ? undefined
    : flat
      ? { color: severityColor(sev) }
      : severityCellStyle(sev);
  return (
    <td>
      <div
        className={`heat-grid-cell${hasValue ? ' clickable viz-focusable' : ' empty'}`}
        style={style}
        onClick={() => hasValue && onCellClick?.({ row, severity: sev })}
        onKeyDown={hasValue ? activateOnKey(() => onCellClick?.({ row, severity: sev })) : undefined}
        role={hasValue ? 'button' : undefined}
        tabIndex={hasValue ? 0 : undefined}
        aria-label={t(pluralKey(count, 'heatGrid.severityCellAriaOne', 'heatGrid.severityCellAria'), { severity: sev, count, label: rowLabel(row) })}
      >
        {count || '—'}
      </div>
    </td>
  );
}

function ViolationsCell({ row, onCellClick }) {
  const hasValue = row.violations > 0;
  return (
    <td>
      <div
        className={`heat-grid-num${hasValue ? ' clickable viz-focusable' : ''}`}
        onClick={() => hasValue && onCellClick?.({ row, severity: null })}
        onKeyDown={hasValue ? activateOnKey(() => onCellClick?.({ row, severity: null })) : undefined}
        role={hasValue ? 'button' : undefined}
        tabIndex={hasValue ? 0 : undefined}
        aria-label={hasValue ? t(violationsAriaKey(row.violations), { count: row.violations, label: rowLabel(row) }) : undefined}
      >
        {row.violations}
      </div>
    </td>
  );
}

function HealthCell({ row, total, rate, flat }) {
  return (
    <td>
      <div
        className={`heat-grid-cell${total > 0 ? ' health' : ' empty'}`}
        style={
          total === 0
            ? undefined
            : flat
              ? { color: complianceRateColor(row.complianceRate) }
              : complianceRateCellStyle(row.complianceRate)
        }
      >
        {rate}
      </div>
    </td>
  );
}

// The two render treatments this component and its callers (HeatGridView,
// DimensionHeatGridView, ViolationsPage) pass as `variant`.
export const HEAT_GRID_VARIANT = Object.freeze({ HEAT: 'heat', FLAT: 'flat' });

/**
 * Column-header click handler shared by the map and violations heat grids
 * (HeatGridView.jsx, DimensionHeatGridView.jsx): clicking the active column
 * flips its direction; clicking a different column selects it, defaulting to
 * ascending only for `ascCol` (the name column in both grids).
 */
export function makeColumnSortHandler({ sortCol, setSortCol, setSortDir, ascCol }) {
  return (col) => {
    if (sortCol === col) {
      setSortDir((d) => (d === SORT_DIR.ASC ? SORT_DIR.DESC : SORT_DIR.ASC));
    } else {
      setSortCol(col);
      setSortDir(col === ascCol ? SORT_DIR.ASC : SORT_DIR.DESC);
    }
  };
}

export default function HeatGridCells({ row, onCellClick, variant = HEAT_GRID_VARIANT.HEAT }) {
  const total = row.violations + row.compliance;
  const rate = total > 0 ? Math.round(row.complianceRate * PERCENT) + '%' : '—';
  const flat = variant === HEAT_GRID_VARIANT.FLAT;

  return (
    <>
      {SEVERITY_ORDER.map((sev) => (
        <SeverityCell key={sev} row={row} sev={sev} flat={flat} onCellClick={onCellClick} />
      ))}
      <ViolationsCell row={row} onCellClick={onCellClick} />
      <HealthCell row={row} total={total} rate={rate} flat={flat} />
    </>
  );
}
