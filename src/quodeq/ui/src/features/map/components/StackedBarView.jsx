import { useMemo, useState } from 'react';

const MAX = 20;
const NW = 180, BW = 320, CW = 48, HW = 80, LW = 40, G = 8, RH = 28, PT = 8;
const TW = NW + G + BW + G + CW + G + HW + G + LW;
const SEGS = [['critical','var(--map-critical)'],['major','var(--map-major)'],['minor','var(--map-minor)']];

export default function StackedBarView({ node, viewMode, onDrillDown }) {
  const [tip, setTip] = useState(null);

  const { rows, more } = useMemo(() => {
    const items = node.children?.length > 0 ? node.children : [node];
    const sorted = [...items].sort((a, b) => b.violations - a.violations);
    return { rows: sorted.slice(0, MAX), more: Math.max(0, sorted.length - MAX) };
  }, [node]);

  if (!rows.length) return <p className="empty-state">No data available for this view.</p>;

  const maxV = Math.max(1, rows[0].violations);
  const totalH = PT + rows.length * RH + (more ? RH : 0) + PT;

  return (
    <div style={{ position: 'relative', overflowX: 'auto' }}>
      <svg viewBox={`0 0 ${TW} ${totalH}`} style={{ width: '100%', minWidth: TW, display: 'block' }}>
        {rows.map((row, i) => {
          const y = PT + i * RH, mid = y + RH / 2;
          const canDrill = !row.isFile && row.children?.length > 0;
          const sev = row.severity || {};
          const total = row.violations || 0;
          const rate = row.complianceRate ?? 0;
          const hx = NW + G + BW + G + CW + G;
          let sx = NW + G;

          return (
            <g key={row.path || row.name}>
              <rect x={0} y={y} width={TW} height={RH - 2} rx={3}
                fill={i % 2 === 0 ? 'var(--color-surface-alt)' : 'none'} />

              <text x={NW - 4} y={mid} textAnchor="end" dominantBaseline="central" fontSize={10}
                fill={canDrill ? 'var(--color-accent)' : 'var(--color-text)'}
                style={{ cursor: canDrill ? 'pointer' : 'default', fontFamily: 'var(--font-mono,monospace)' }}
                onClick={() => canDrill && onDrillDown?.(row.path)}>
                {row.name?.length > 24 ? row.name.slice(0, 22) + '…' : row.name}
              </text>

              <rect x={NW + G} y={mid - 7} width={BW} height={14} rx={3} fill="var(--color-surface-alt)" />

              {SEGS.map(([key, color]) => {
                const val = sev[key] || 0;
                if (!val) return null;
                const w = (val / maxV) * BW;
                const el = <rect key={key} x={sx} y={mid - 7} width={w} height={14}
                  fill={color} style={{ cursor: 'pointer' }}
                  onMouseEnter={(e) => setTip({ x: e.clientX, y: e.clientY, text: `${key}: ${val}` })}
                  onMouseLeave={() => setTip(null)} />;
                sx += w;
                return el;
              })}

              <text x={NW + G + BW + G + CW / 2} y={mid} textAnchor="middle" dominantBaseline="central"
                fontSize={10} fontWeight="600" fill="var(--color-text)">{total}</text>

              <rect x={hx} y={mid - 4} width={HW} height={8} rx={4} fill="var(--color-surface-alt)" />
              <rect x={hx} y={mid - 4} width={Math.round(rate * HW)} height={8} rx={4} fill="var(--map-clean)" />

              <text x={hx + HW + G} y={mid} textAnchor="start" dominantBaseline="central"
                fontSize={10} fill="var(--color-text-muted)">{Math.round(rate * 100)}%</text>
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
          {tip.text}
        </div>
      )}
    </div>
  );
}
