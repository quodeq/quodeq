import { useMemo } from 'react';
import { complianceRateColor } from '../utils/mapColors.js';

export default function HeatGridView({ node, viewMode, onDrillDown }) {
  const rows = useMemo(() => {
    const items = node.children.length > 0 ? node.children : [node];
    return items
      .filter((r) => r.violations > 0 || r.compliance > 0)
      .sort((a, b) => {
        // 1 critical > many major, 1 major > many minor
        const sevScore = (r) => r.severity.critical * 10000 + r.severity.major * 100 + r.severity.minor;
        const diff = sevScore(b) - sevScore(a);
        if (diff !== 0) return diff;
        return (a.name || '').localeCompare(b.name || '');
      });
  }, [node]);

  if (rows.length === 0) {
    return <p className="empty-state">No data available for this view.</p>;
  }

  const isViolations = viewMode === 'violations';

  return (
    <div className="heat-grid-wrap">
      <table className="heat-grid">
        <thead>
          <tr>
            <th>File / Folder</th>
            {isViolations ? (
              <>
                <th>Critical</th>
                <th>Major</th>
                <th>Minor</th>
                <th>Compliance</th>
                <th>Total</th>
                <th>Health</th>
              </>
            ) : (
              <>
                <th>Violations</th>
                <th>Compliance</th>
                <th>Total</th>
                <th>Rate</th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const canDrill = !row.isFile && row.children?.length > 0;
            const total = row.violations + row.compliance;
            const rate = total > 0 ? Math.round(row.complianceRate * 100) + '%' : '—';

            return (
              <tr key={row.path}>
                <td>
                  <div
                    className={`heat-grid-file${canDrill ? ' clickable' : ''}`}
                    role={canDrill ? 'button' : undefined}
                    tabIndex={canDrill ? 0 : undefined}
                    onClick={() => canDrill && onDrillDown(row.path)}
                    onKeyDown={(e) => e.key === 'Enter' && canDrill && onDrillDown(row.path)}
                    title={row.path}
                  >
                    {row.isFile ? '' : '\uD83D\uDCC1 '}{row.name}
                  </div>
                </td>
                {isViolations ? (
                  <>
                    <td><div className={`heat-grid-cell${row.severity.critical > 0 ? '' : ' empty'}`} style={row.severity.critical > 0 ? { background: 'var(--map-critical)' } : undefined}>{row.severity.critical || '—'}</div></td>
                    <td><div className={`heat-grid-cell${row.severity.major > 0 ? '' : ' empty'}`} style={row.severity.major > 0 ? { background: 'var(--map-major)' } : undefined}>{row.severity.major || '—'}</div></td>
                    <td><div className={`heat-grid-cell${row.severity.minor > 0 ? '' : ' empty'}`} style={row.severity.minor > 0 ? { background: 'var(--map-minor)' } : undefined}>{row.severity.minor || '—'}</div></td>
                    <td><div className={`heat-grid-cell${row.compliance > 0 ? '' : ' empty'}`} style={row.compliance > 0 ? { background: 'var(--map-clean)' } : undefined}>{row.compliance || '—'}</div></td>
                    <td><div className="heat-grid-num">{row.violations}</div></td>
                    <td><div className={`heat-grid-cell${total > 0 ? '' : ' empty'}`} style={total > 0 ? { background: complianceRateColor(row.complianceRate) } : undefined}>{rate}</div></td>
                  </>
                ) : (
                  <>
                    <td><div className="heat-grid-num">{row.violations}</div></td>
                    <td><div className="heat-grid-num">{row.compliance}</div></td>
                    <td><div className="heat-grid-num">{total}</div></td>
                    <td><div className={`heat-grid-cell${total > 0 ? '' : ' empty'}`} style={total > 0 ? { background: complianceRateColor(row.complianceRate) } : undefined}>{rate}</div></td>
                  </>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
