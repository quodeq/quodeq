import { useMemo } from 'react';
import { complianceRateColor } from '../utils/mapColors.js';

function cellColor(dimData, viewMode) {
  if (!dimData) return null;
  if (viewMode === 'violations') {
    if (dimData.violations === 0) return null;
    if (dimData.violations >= 5) return 'var(--map-critical)';
    if (dimData.violations >= 2) return 'var(--map-major)';
    return 'var(--map-minor)';
  }
  const total = dimData.violations + dimData.compliance;
  if (total === 0) return null;
  const rate = dimData.compliance / total;
  return complianceRateColor(rate);
}

function cellLabel(dimData, viewMode) {
  if (!dimData) return '';
  if (viewMode === 'violations') return dimData.violations || '';
  if (viewMode === 'compliance') return dimData.compliance || '';
  const total = dimData.violations + dimData.compliance;
  if (total === 0) return '';
  return Math.round((dimData.compliance / total) * 100) + '%';
}

export default function HeatGridView({ node, viewMode, onDrillDown }) {
  const { rows, dimensionNames } = useMemo(() => {
    const dimSet = new Set();
    const items = node.children.length > 0 ? node.children : [node];
    for (const child of items) {
      for (const dim of Object.keys(child.dimensions || {})) {
        dimSet.add(dim);
      }
    }
    const names = [...dimSet].sort();
    return { rows: items, dimensionNames: names };
  }, [node]);

  if (dimensionNames.length === 0) {
    return <p className="empty-state">No dimension data available for this view.</p>;
  }

  return (
    <div className="heat-grid-wrap">
      <table className="heat-grid">
        <thead>
          <tr>
            <th>File / Folder</th>
            {dimensionNames.map((dim) => <th key={dim}>{dim}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const canDrill = !row.isFile && row.children?.length > 0;
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
                    {row.isFile ? '' : '📁 '}{row.name}
                  </div>
                </td>
                {dimensionNames.map((dim) => {
                  const dimData = row.dimensions?.[dim];
                  const bg = cellColor(dimData, viewMode);
                  const label = cellLabel(dimData, viewMode);
                  return (
                    <td key={dim}>
                      <div
                        className={`heat-grid-cell${!bg ? ' empty' : ''}`}
                        style={bg ? { background: bg } : undefined}
                        title={`${row.name} × ${dim}: ${dimData?.violations || 0}v / ${dimData?.compliance || 0}c`}
                      >
                        {label || '—'}
                      </div>
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
