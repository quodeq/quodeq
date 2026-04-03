import { useMemo, useState } from 'react';

const PALETTE = ['#e8795a', '#5a9be8', '#5ae8a0', '#e8d95a', '#b85ae8', '#e85a8f', '#5ae8e8', '#a0e85a'];
const RINGS = [0.25, 0.5, 0.75, 1];
const CX = 150, CY = 150, R = 120;

function polarXY(angle, radius) {
  return [CX + radius * Math.cos(angle), CY + radius * Math.sin(angle)];
}

export default function RadarView({ node, viewMode, onDrillDown }) {
  const [tooltip, setTooltip] = useState(null);

  const dims = useMemo(() => Object.keys(node.dimensions || {}), [node]);
  const items = useMemo(() => (node.children?.length > 0 ? node.children : [node]), [node]);

  const maxViolations = useMemo(() => {
    let max = 1;
    for (const child of items) {
      for (const dim of dims) {
        const d = child.dimensions?.[dim];
        if (d && d.violations > max) max = d.violations;
      }
    }
    return max;
  }, [items, dims]);

  if (dims.length < 3) {
    return <p className="empty-state">Need at least 3 dimensions for radar view.</p>;
  }

  const angleStep = (2 * Math.PI) / dims.length;
  const startAngle = -Math.PI / 2;

  const getValue = (child, dim) => {
    const d = child.dimensions?.[dim];
    if (!d) return 0;
    if (viewMode === 'health') {
      const total = d.violations + d.compliance;
      return total > 0 ? d.compliance / total : 0;
    }
    return 1 - d.violations / maxViolations;
  };

  const shapes = items.map((child, ci) => {
    const color = PALETTE[ci % PALETTE.length];
    const points = dims.map((dim, di) => {
      const angle = startAngle + di * angleStep;
      const val = getValue(child, dim);
      return { xy: polarXY(angle, R * val), val, dim, child };
    });
    const polyStr = points.map((p) => p.xy.join(',')).join(' ');
    return { child, color, points, polyStr };
  });

  return (
    <div style={{ position: 'relative' }}>
      <svg viewBox="0 0 300 300" style={{ width: '100%', maxWidth: 500 }}>
        {/* grid rings */}
        {RINGS.map((r) => (
          <circle key={r} cx={CX} cy={CY} r={R * r} fill="none" stroke="#e0e0e0" strokeWidth={0.5} />
        ))}
        {/* axis lines + labels */}
        {dims.map((dim, di) => {
          const angle = startAngle + di * angleStep;
          const [ex, ey] = polarXY(angle, R);
          const [lx, ly] = polarXY(angle, R + 14);
          return (
            <g key={dim}>
              <line x1={CX} y1={CY} x2={ex} y2={ey} stroke="#ccc" strokeWidth={0.5} />
              <text x={lx} y={ly} textAnchor="middle" dominantBaseline="central" fontSize={7} fill="#666">
                {dim.length > 12 ? dim.slice(0, 11) + '…' : dim}
              </text>
            </g>
          );
        })}
        {/* shapes */}
        {shapes.map(({ child, color, points, polyStr }) => (
          <g key={child.path || child.name}>
            <polygon points={polyStr} fill={color} fillOpacity={0.18} stroke={color} strokeWidth={1.2} />
            {points.map((p, i) => (
              <circle key={i} cx={p.xy[0]} cy={p.xy[1]} r={3} fill={color} stroke="#fff" strokeWidth={0.5}
                style={{ cursor: 'pointer' }}
                onMouseEnter={(e) => setTooltip({
                  x: e.clientX, y: e.clientY,
                  text: `${child.name} — ${p.dim}: ${viewMode === 'health'
                    ? (p.val * 100).toFixed(1) + '%' : child.dimensions?.[p.dim]?.violations ?? 0}`,
                })}
                onMouseLeave={() => setTooltip(null)}
                onClick={() => child.children?.length > 0 && onDrillDown?.(child.path)}
              />
            ))}
          </g>
        ))}
      </svg>
      {/* legend */}
      <div style={{ position: 'absolute', top: 4, left: 4, fontSize: 10, lineHeight: '16px' }}>
        {shapes.map(({ child, color }) => (
          <div key={child.path || child.name} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, display: 'inline-block' }} />
            <span style={{ cursor: child.children?.length > 0 ? 'pointer' : 'default' }}
              onClick={() => child.children?.length > 0 && onDrillDown?.(child.path)}>
              {child.name}
            </span>
          </div>
        ))}
      </div>
      {/* tooltip */}
      {tooltip && (
        <div className="map-tooltip" style={{ position: 'fixed', left: tooltip.x + 10, top: tooltip.y - 20 }}>
          {tooltip.text}
        </div>
      )}
    </div>
  );
}
