import { severityCellStyle, complianceRateCellStyle, severityColor, complianceRateColor } from '../core/mapColors.js';

const SEVERITY_LEVELS = ['critical', 'major', 'minor'];

/**
 * Renders the severity + violations + health cells for a heat grid row.
 *
 * Shared between HeatGridView (file tree) and DimensionHeatGridView
 * (violations). Pass `variant="flat"` to get the text-only variant used
 * by the Violations tab's by-dimension and by-file tables. The Map
 * page's own file-tree keeps the default filled-heat variant.
 */
export default function HeatGridCells({ row, onCellClick, variant = 'heat' }) {
  const total = row.violations + row.compliance;
  const rate = total > 0 ? Math.round(row.complianceRate * 100) + '%' : '—';
  const flat = variant === 'flat';

  return (
    <>
      {SEVERITY_LEVELS.map((sev) => {
        const count = row.severity[sev];
        const hasValue = count > 0;
        const style = !hasValue
          ? undefined
          : flat
            ? { color: severityColor(sev) }
            : severityCellStyle(sev);
        return (
          <td key={sev}>
            <div
              className={`heat-grid-cell${hasValue ? ' clickable viz-focusable' : ' empty'}`}
              style={style}
              onClick={() => hasValue && onCellClick?.({ row, severity: sev })}
              role={hasValue ? 'button' : undefined}
              tabIndex={hasValue ? 0 : undefined}
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
    </>
  );
}
