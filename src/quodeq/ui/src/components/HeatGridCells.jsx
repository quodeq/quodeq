import { severityCellStyle, complianceRateCellStyle, severityColor, complianceRateColor } from '../features/map/viz/core/mapColors.js';

const SEVERITY_LEVELS = ['critical', 'major', 'minor'];

/**
 * Renders the severity + violations + health cells for a heat grid row.
 * Shared between HeatGridView (file tree) and DimensionHeatGridView (violations).
 *
 * The two consumers want different visual weights: the file-tree view
 * keeps the filled "heat-map" cells, while the violations table wants a
 * leaner text-only treatment. Pass `variant="flat"` to opt into the
 * text-only variant.
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
              className={`heat-grid-cell${hasValue ? ' clickable' : ' empty'}`}
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
          className={`heat-grid-num${row.violations > 0 ? ' clickable' : ''}`}
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
