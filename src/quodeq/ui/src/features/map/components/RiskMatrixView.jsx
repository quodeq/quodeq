import { useMemo, useState } from 'react';
import { nodeColor } from '../utils/mapColors.js';

const W = 500, H = 340, PAD = { l: 50, r: 20, t: 30, b: 50 };
const PW = W - PAD.l - PAD.r, PH = H - PAD.t - PAD.b;

export default function RiskMatrixView({ node, viewMode, onDrillDown }) {
  const [tip, setTip] = useState(null);

  const items = useMemo(() => (node.children?.length > 0 ? node.children : [node]), [node]);

  const { points, maxX, maxY, maxB } = useMemo(() => {
    const pts = items.map((c) => ({
      child: c,
      x: c.violations || 0,
      y: (c.severity?.critical || 0) * 100 + (c.severity?.major || 0) * 10 + (c.severity?.minor || 0),
      b: (c.violations || 0) + (c.compliance || 0),
      color: nodeColor(c, viewMode),
    }));
    return {
      points: pts,
      maxX: Math.max(1, ...pts.map((p) => p.x)),
      maxY: Math.max(1, ...pts.map((p) => p.y)),
      maxB: Math.max(1, ...pts.map((p) => p.b)),
    };
  }, [items, viewMode]);

  const px = (x) => PAD.l + (x / maxX) * PW;
  const py = (y) => PAD.t + PH - (y / maxY) * PH;
  const br = (b) => 6 + (b / maxB) * 16;

  return (
    <div style={{ position: 'relative' }}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', maxWidth: W, display: 'block' }}>
        {/* quadrant backgrounds */}
        <rect x={PAD.l + PW / 2} y={PAD.t} width={PW / 2} height={PH / 2} fill="rgba(220,50,50,0.07)" />
        <rect x={PAD.l} y={PAD.t + PH / 2} width={PW / 2} height={PH / 2} fill="rgba(50,180,80,0.07)" />

        {/* quadrant labels */}
        <text x={PAD.l + PW * 0.75} y={PAD.t + 14} textAnchor="middle" fontSize={9} fill="#c0392b" fontWeight="600">
          ⚠ Fix first
        </text>
        <text x={PAD.l + PW * 0.25} y={PAD.t + PH - 8} textAnchor="middle" fontSize={9} fill="#27ae60" fontWeight="600">
          ✓ Low priority
        </text>

        {/* quadrant dividers */}
        <line x1={PAD.l + PW / 2} y1={PAD.t} x2={PAD.l + PW / 2} y2={PAD.t + PH} stroke="#ddd" strokeWidth={0.8} strokeDasharray="4,3" />
        <line x1={PAD.l} y1={PAD.t + PH / 2} x2={PAD.l + PW} y2={PAD.t + PH / 2} stroke="#ddd" strokeWidth={0.8} strokeDasharray="4,3" />

        {/* axes */}
        <line x1={PAD.l} y1={PAD.t + PH} x2={PAD.l + PW} y2={PAD.t + PH} stroke="#aaa" strokeWidth={1} />
        <line x1={PAD.l} y1={PAD.t} x2={PAD.l} y2={PAD.t + PH} stroke="#aaa" strokeWidth={1} />

        {/* axis labels */}
        <text x={PAD.l + PW / 2} y={H - 4} textAnchor="middle" fontSize={10} fill="#555">Violations →</text>
        <text x={10} y={PAD.t + PH / 2} textAnchor="middle" fontSize={10} fill="#555"
          transform={`rotate(-90, 10, ${PAD.t + PH / 2})`}>Severity Score →</text>

        {/* bubbles */}
        {points.map(({ child, x, y, b, color }) => {
          const cx = px(x), cy = py(y), r = br(b);
          const canDrill = !child.isFile && child.children?.length > 0;
          return (
            <g key={child.path || child.name}>
              <circle cx={cx} cy={cy} r={r} fill={color} fillOpacity={0.75} stroke="#fff" strokeWidth={1}
                style={{ cursor: canDrill ? 'pointer' : 'default' }}
                onMouseEnter={(e) => setTip({ x: e.clientX, y: e.clientY, name: child.name, viol: x, sev: y, total: b })}
                onMouseLeave={() => setTip(null)}
                onClick={() => canDrill && onDrillDown?.(child.path)} />
              {x >= 4 && (
                <text cx={cx} cy={cy} x={cx} y={cy + 1} textAnchor="middle" dominantBaseline="central"
                  fontSize={7} fill="#fff" fontWeight="600" style={{ pointerEvents: 'none' }}>
                  {child.name?.length > 8 ? child.name.slice(0, 7) + '…' : child.name}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      {tip && (
        <div className="map-tooltip" style={{ position: 'fixed', left: tip.x + 10, top: tip.y - 28 }}>
          <strong>{tip.name}</strong><br />
          Violations: {tip.viol} · Severity: {tip.sev} · Total: {tip.total}
        </div>
      )}
    </div>
  );
}
