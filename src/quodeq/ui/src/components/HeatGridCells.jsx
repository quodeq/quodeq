import { severityCellStyle, complianceRateCellStyle, severityColor, complianceRateColor } from '../features/map/viz/core/mapColors.js';

const SEVERITY_LEVELS = ['critical', 'major', 'minor'];

/**
 * Renders the severity + violations + health cells for a heat grid row.
 *
 * Single shared component for both heat grids:
 *  - HeatGridView (Map page file tree) — default filled "heat" variant.
 *  - DimensionHeatGridView (Violations tab by-dimension/by-file tables) —
 *    pass `variant="flat"` for the leaner text-only treatment.
 *
 * This used to be two copies (one here, one under features/map/viz/components)
 * that drifted apart: the violations copy gained keyboard activation + aria
 * labels while the map copy gained the `viz-focusable` keyboard focus ring.
 * They were merged into this file so every clickable cell in both grids gets
 * the same treatment — keep it that way rather than re-forking.
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
              onKeyDown={hasValue ? (e) => {
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onCellClick?.({ row, severity: sev }); }
              } : undefined}
              role={hasValue ? 'button' : undefined}
              tabIndex={hasValue ? 0 : undefined}
              aria-label={`${sev}: ${count} violation${count !== 1 ? 's' : ''} in ${row.name || 'row'}`}
            >
              {count || '—'}
            </div>
          </td>
        );
      })}
      <td>
        <div
          className={`heat-grid-num${row.violations > 0 ? ' clickable viz-focusable' : ''}`}
          onClick={() => row.violations > 0 && onCellClick?.({ row, severity: null })}
          onKeyDown={row.violations > 0 ? (e) => {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onCellClick?.({ row, severity: null }); }
          } : undefined}
          role={row.violations > 0 ? 'button' : undefined}
          tabIndex={row.violations > 0 ? 0 : undefined}
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
