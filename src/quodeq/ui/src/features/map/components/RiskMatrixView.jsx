import { useMemo, useState, useEffect } from 'react';
import { nodeColor } from '../utils/mapColors.js';

const W = 600, H = 420, PAD = { l: 55, r: 25, t: 35, b: 55 };
const PW = W - PAD.l - PAD.r, PH = H - PAD.t - PAD.b;

export default function RiskMatrixView({ node, viewMode, onDrillDown }) {
  const [tip, setTip] = useState(null);
  const [entered, setEntered] = useState(false);

  useEffect(() => { const t = setTimeout(() => setEntered(true), 50); return () => clearTimeout(t); }, []);

  const items = useMemo(() => (node.children?.length > 0 ? node.children : [node]), [node]);

  const { points, maxX, maxY, maxB } = useMemo(() => {
    const pts = items.map((c) => ({
      child: c,
      x: c.violations || 0,
      y: (c.severity?.critical || 0) * 100 + (c.severity?.major || 0) * 10 + (c.severity?.minor || 0),
      b: (c.violations || 0) + (c.compliance || 0),
      color: nodeColor(c, viewMode),
      hasCritical: (c.severity?.critical || 0) > 0,
    }));
    return {
      points: pts,
      maxX: Math.max(1, ...pts.map((p) => p.x)) * 1.15,
      maxY: Math.max(1, ...pts.map((p) => p.y)) * 1.15,
      maxB: Math.max(1, ...pts.map((p) => p.b)),
    };
  }, [items, viewMode]);

  const px = (x) => PAD.l + (x / maxX) * PW;
  const py = (y) => PAD.t + PH - (y / maxY) * PH;
  const br = (b) => 8 + (b / maxB) * 20;

  return (
    <div style={{ position: 'relative' }}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', display: 'block' }}>
        <defs>
          <radialGradient id="riskDanger" cx="100%" cy="0%" r="100%">
            <stop offset="0%" stopColor="#e74c3c" stopOpacity="0.12" />
            <stop offset="100%" stopColor="#e74c3c" stopOpacity="0" />
          </radialGradient>
          <radialGradient id="riskSafe" cx="0%" cy="100%" r="100%">
            <stop offset="0%" stopColor="#2ecc71" stopOpacity="0.10" />
            <stop offset="100%" stopColor="#2ecc71" stopOpacity="0" />
          </radialGradient>
          <filter id="glow">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        {/* Gradient quadrant fills */}
        <rect x={PAD.l} y={PAD.t} width={PW} height={PH} fill="url(#riskDanger)" />
        <rect x={PAD.l} y={PAD.t} width={PW} height={PH} fill="url(#riskSafe)" />

        {/* Grid lines */}
        {[0.25, 0.5, 0.75].map((f) => (
          <g key={f} opacity={0.3}>
            <line x1={PAD.l} y1={PAD.t + PH * (1 - f)} x2={PAD.l + PW} y2={PAD.t + PH * (1 - f)} stroke="var(--color-border)" strokeWidth={0.5} />
            <line x1={PAD.l + PW * f} y1={PAD.t} x2={PAD.l + PW * f} y2={PAD.t + PH} stroke="var(--color-border)" strokeWidth={0.5} />
          </g>
        ))}

        {/* Quadrant labels */}
        <text x={PAD.l + PW - 8} y={PAD.t + 18} textAnchor="end" fontSize={10} fill="rgba(231,76,60,0.6)" fontWeight="600">Fix first</text>
        <text x={PAD.l + 8} y={PAD.t + PH - 8} textAnchor="start" fontSize={10} fill="rgba(46,204,113,0.6)" fontWeight="600">Low priority</text>

        {/* Axes */}
        <line x1={PAD.l} y1={PAD.t + PH} x2={PAD.l + PW} y2={PAD.t + PH} stroke="var(--color-border)" strokeWidth={1} />
        <line x1={PAD.l} y1={PAD.t} x2={PAD.l} y2={PAD.t + PH} stroke="var(--color-border)" strokeWidth={1} />
        <text x={PAD.l + PW / 2} y={H - 8} textAnchor="middle" fontSize={11} fill="var(--color-text-muted)">Violations →</text>
        <text x={14} y={PAD.t + PH / 2} textAnchor="middle" fontSize={11} fill="var(--color-text-muted)" transform={`rotate(-90, 14, ${PAD.t + PH / 2})`}>Severity →</text>

        {/* Bubbles with entrance animation */}
        {points.map(({ child, x, y, b, color, hasCritical }, i) => {
          const cx = px(x), cy = py(y), r = br(b);
          const canDrill = !child.isFile && child.children?.length > 0;
          const delay = i * 60;
          return (
            <g key={child.path || child.name}
              style={{ opacity: entered ? 1 : 0, transform: entered ? 'none' : `translate(${cx - W / 2}px, ${cy - H / 2}px) scale(0)`, transformOrigin: `${cx}px ${cy}px`, transition: `opacity 0.5s ease ${delay}ms, transform 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) ${delay}ms` }}>
              {hasCritical && <circle cx={cx} cy={cy} r={r + 4} fill="none" stroke={color} strokeWidth={1} opacity={0.3}>
                <animate attributeName="r" values={`${r + 2};${r + 8};${r + 2}`} dur="2s" repeatCount="indefinite" />
                <animate attributeName="opacity" values="0.3;0.1;0.3" dur="2s" repeatCount="indefinite" />
              </circle>}
              {canDrill ? (
                /* Folder: rounded rectangle */
                <>
                  <rect x={cx - r} y={cy - r * 0.8} width={r * 2} height={r * 1.6} rx={4}
                    fill={color} fillOpacity={0.8} stroke="rgba(255,255,255,0.25)" strokeWidth={1.5}
                    filter={tip?.name === child.name ? 'url(#glow)' : undefined}
                    style={{ cursor: 'pointer', transition: 'fill-opacity 0.2s ease' }}
                    onMouseEnter={(e) => setTip({ x: e.clientX, y: e.clientY, child })}
                    onMouseMove={(e) => setTip((t) => t ? { ...t, x: e.clientX, y: e.clientY } : null)}
                    onMouseLeave={() => setTip(null)}
                    onClick={() => onDrillDown?.(child.path)} />
                  {/* Folder tab */}
                  <rect x={cx - r} y={cy - r * 0.8 - 4} width={r * 0.7} height={5} rx={2}
                    fill={color} fillOpacity={0.6} style={{ pointerEvents: 'none' }} />
                </>
              ) : (
                /* File: circle */
                <circle cx={cx} cy={cy} r={r} fill={color} fillOpacity={0.8}
                  stroke="rgba(255,255,255,0.2)" strokeWidth={1.5}
                  filter={tip?.name === child.name ? 'url(#glow)' : undefined}
                  style={{ cursor: 'default', transition: 'fill-opacity 0.2s ease' }}
                  onMouseEnter={(e) => setTip({ x: e.clientX, y: e.clientY, child })}
                  onMouseMove={(e) => setTip((t) => t ? { ...t, x: e.clientX, y: e.clientY } : null)}
                  onMouseLeave={() => setTip(null)} />
              )}
              {r > 14 && (
                <text x={cx} y={cy + 1} textAnchor="middle" dominantBaseline="central"
                  fontSize={Math.min(10, r / 2)} fill="#fff" fontWeight="600" style={{ pointerEvents: 'none' }}>
                  {child.name?.length > r / 3 ? child.name.slice(0, Math.floor(r / 3)) + '…' : child.name}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      {tip && (() => {
        const c = tip.child;
        const total = c.violations + c.compliance;
        const rate = total > 0 ? Math.round(c.compliance / total * 100) : 0;
        return (
          <div className="map-tooltip" style={{ position: 'fixed', left: tip.x + 12, top: tip.y - 12 }}>
            <div className="map-tooltip-title">{c.path || c.name}</div>
            <div className="map-tooltip-row"><span>Violations</span><span>{c.violations}</span></div>
            <div className="map-tooltip-row"><span>Compliance</span><span>{c.compliance}</span></div>
            <div className="map-tooltip-row"><span>Health</span><span>{rate}%</span></div>
            {c.severity?.critical > 0 && <div className="map-tooltip-row"><span>Critical</span><span>{c.severity.critical}</span></div>}
            {c.severity?.major > 0 && <div className="map-tooltip-row"><span>Major</span><span>{c.severity.major}</span></div>}
            {c.severity?.minor > 0 && <div className="map-tooltip-row"><span>Minor</span><span>{c.severity.minor}</span></div>}
          </div>
        );
      })()}
    </div>
  );
}
