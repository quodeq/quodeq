import { severityCellStyle, complianceRateCellStyle } from '../features/map/viz/core/mapColors.js';

const SEVERITY_LEVELS = ['critical', 'major', 'minor'];

/**
 * Renders the severity + violations + health cells for a heat grid row.
 * Shared between HeatGridView (file tree) and DimensionHeatGridView (violations).
 */
export default function HeatGridCells({ row, onCellClick }) {
  const total = row.violations + row.compliance;
  const rate = total > 0 ? Math.round(row.complianceRate * 100) + '%' : '—';

  return (
    <>
      {SEVERITY_LEVELS.map((sev) => {
        const count = row.severity[sev];
        const hasValue = count > 0;
        return (
          <td key={sev}>
            <div
              className={`heat-grid-cell${hasValue ? ' clickable' : ' empty'}`}
              style={hasValue ? severityCellStyle(sev) : undefined}
              onClick={() => hasValue && onCellClick?.({ row, severity: sev })}
              role={hasValue ? 'button' : undefined}
              aria-label={`${sev}: ${count} violation${count !== 1 ? 's' : ''} in ${row.name || 'row'}`}
            >
              {count || '—'}
            </div>
          </td>
        );
      })}
      <td>
        <div
          className={`heat-grid-num${row.violations > 0 ? ' clickable' : ''}`}
          onClick={() => row.violations > 0 && onCellClick?.({ row, severity: null })}
          role={row.violations > 0 ? 'button' : undefined}
        >
          {row.violations}
        </div>
      </td>
      <td>
        <div
          className={`heat-grid-cell${total > 0 ? ' health' : ' empty'}`}
          style={total > 0 ? complianceRateCellStyle(row.complianceRate) : undefined}
        >
          {rate}
        </div>
      </td>
    </>
  );
}
