import { useMemo, useState } from 'react';

const MAX_ROWS = 15;
const NW = 150, TW_TRACK = 320, G = 12, RH = 22, PT = 8;
const TOTAL_W = NW + G + TW_TRACK + G;
const dotColor = (i, crit, maj) => i < crit ? '#e53e3e' : i < crit + maj ? '#dd6b20' : '#d69e2e';

export default function DotStripView({ node, viewMode, onDrillDown }) {
  const [tip, setTip] = useState(null);

  const { rows, more } = useMemo(() => {
    const items = node.children?.length > 0 ? node.children : [node];
    const sorted = [...items].filter((c) => c.violations > 0).sort((a, b) => b.violations - a.violations);
    return { rows: sorted.slice(0, MAX_ROWS), more: Math.max(0, sorted.length - MAX_ROWS) };
  }, [node]);

  if (!rows.length) return <p className="empty-state">No data available for this view.</p>;

  const totalH = PT + rows.length * RH + (more ? RH : 0) + PT;

  return (
    <div style={{ position: 'relative', overflowX: 'auto' }}>
      <svg viewBox={`0 0 ${TOTAL_W} ${totalH}`} style={{ width: '100%', minWidth: TOTAL_W, display: 'block' }}>
        {rows.map((row, i) => {
          const y = PT + i * RH, mid = y + RH / 2;
          const canDrill = !row.isFile && row.children?.length > 0;
          const n = row.violations, crit = row.severity?.critical || 0, maj = row.severity?.major || 0;
          return (
            <g key={row.path || row.name}>
              <rect x={0} y={y} width={TOTAL_W} height={RH - 2} rx={2}
                fill={i % 2 === 0 ? 'var(--color-surface-alt)' : 'none'} />
              <text x={NW - 4} y={mid} textAnchor="end" dominantBaseline="central" fontSize={10}
                fill={canDrill ? 'var(--color-accent)' : 'var(--color-text)'}
                style={{ cursor: canDrill ? 'pointer' : 'default', fontFamily: 'var(--font-mono,monospace)' }}
                onClick={() => canDrill && onDrillDown?.(row.path)}>
                {row.name?.length > 20 ? row.name.slice(0, 18) + '…' : row.name}
              </text>
              <rect x={NW + G} y={mid - 1} width={TW_TRACK} height={2} rx={1} fill="var(--color-surface-alt)" />
              {Array.from({ length: n }, (_, di) => {
                const dotX = NW + G + (n === 1 ? TW_TRACK / 2 : (di / (n - 1)) * TW_TRACK);
                const sev = di < crit ? 'critical' : di < crit + maj ? 'major' : 'minor';
                return (
                  <circle key={di} cx={dotX} cy={mid} r={2.5} fill={dotColor(di, crit, maj)}
                    stroke="#fff" strokeWidth={0.5}
                    onMouseEnter={(e) => setTip({ x: e.clientX, y: e.clientY, name: row.name, sev })}
                    onMouseLeave={() => setTip(null)} />
                );
              })}
            </g>
          );
        })}
        {more > 0 && (
          <text x={NW + G} y={PT + rows.length * RH + RH / 2} dominantBaseline="central"
            fontSize={10} fill="var(--color-text-muted)">… and {more} more</text>
        )}
      </svg>
      {tip && (
        <div className="map-tooltip" style={{ position: 'fixed', left: tip.x + 10, top: tip.y - 28 }}>
          <strong>{tip.name}</strong> — {tip.sev}
        </div>
      )}
    </div>
  );
}
