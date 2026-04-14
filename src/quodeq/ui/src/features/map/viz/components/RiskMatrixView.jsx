import { useMemo, useState, useEffect } from 'react';
import { nodeColor, nodeBorderColor } from '../core/mapColors.js';
import FileShape from './FileShape.jsx';

const W = 600, H = 420, PAD = { l: 55, r: 25, t: 35, b: 55 };
const PW = W - PAD.l - PAD.r, PH = H - PAD.t - PAD.b;

const COMPLIANCE_DAMPEN = 0.45;
const SEV_WEIGHT_CRITICAL = 100;
const SEV_WEIGHT_MAJOR = 10;
const SEV_WEIGHT_MINOR = 1;
const BUBBLE_RADIUS_MIN = 3;
const BUBBLE_RADIUS_RANGE = 8;
const LABEL_FONT_MAX = 11;
const LABEL_FONT_MIN = 8;
const LABEL_FONT_DIVISOR = 3;
const LABEL_CHAR_WIDTH_FACTOR = 0.55;
const LABEL_PLACED_CAP = 100;
const TOOLTIP_FLIP_X_THRESHOLD = 0.65;
const TOOLTIP_FLIP_Y_THRESHOLD = 0.75;

/* ── Hook: bubble positioning & collision detection ── */

function useBubbleLayout(node) {
  const items = useMemo(() => (node.children?.length > 0 ? node.children : [node]), [node]);

  const { points, maxX, maxY, maxB } = useMemo(() => {
    const pts = items.map((c) => {
      const total = (c.violations || 0) + (c.compliance || 0);
      const dampen = total > 0 ? 1 - (c.compliance / total) * COMPLIANCE_DAMPEN : 1;
      return {
        child: c,
        x: (c.violations || 0) * dampen,
        y: ((c.severity?.critical || 0) * SEV_WEIGHT_CRITICAL + (c.severity?.major || 0) * SEV_WEIGHT_MAJOR + (c.severity?.minor || 0) * SEV_WEIGHT_MINOR) * dampen,
        b: total,
        color: nodeColor(c, 'violations'),
        border: nodeBorderColor(c, 'violations'),
        hasCritical: (c.severity?.critical || 0) > 0,
      };
    });
    return {
      points: pts,
      maxX: Math.max(1, ...pts.map((p) => p.x)) * 1.15,
      maxY: Math.max(1, ...pts.map((p) => p.y)) * 1.15,
      maxB: Math.max(1, ...pts.map((p) => p.b)),
    };
  }, [items]);

  const log = (v, max) => max > 0 ? Math.log1p(v) / Math.log1p(max) : 0;
  const px = (x) => PAD.l + log(x, maxX) * PW;
  const py = (y) => PAD.t + PH - log(y, maxY) * PH;
  const br = (b) => BUBBLE_RADIUS_MIN + (b / maxB) * BUBBLE_RADIUS_RANGE;

  return { points, px, py, br };
}

/* ── Sub-component: SVG bubble circles & labels ── */

function BubbleGroup({ points, px, py, br, entered, showLabels, tip, setTip, onDrillDown, onFileClick }) {
  return (
    <>
      {points.map(({ child, x, y, b, color, border, hasCritical }) => {
        const cx = px(x), cy = py(y), r = br(b);
        const canDrill = !child.isFile && child.children?.length > 0;
        return (
          <g key={child.path || child.name}
            style={{ opacity: entered ? 1 : 0, transition: 'opacity 0.2s ease' }}>
            {hasCritical && <circle cx={cx} cy={cy} r={r + 4} fill="none" stroke={color} strokeWidth={1} opacity={0.3}>
              <animate attributeName="r" values={`${r + 2};${r + 8};${r + 2}`} dur="2s" repeatCount="indefinite" />
              <animate attributeName="opacity" values="0.3;0.1;0.3" dur="2s" repeatCount="indefinite" />
            </circle>}
            {canDrill ? (
              <circle cx={cx} cy={cy} r={r} fill={color} fillOpacity={0.85}
                stroke={border} strokeWidth={1}
                filter={tip?.name === child.name ? 'url(#glow)' : undefined}
                style={{ cursor: 'pointer', transition: 'fill-opacity 0.2s ease' }}
                onMouseEnter={(e) => setTip({ x: e.clientX, y: e.clientY, child })}
                onMouseMove={(e) => setTip((t) => t ? { ...t, x: e.clientX, y: e.clientY } : null)}
                onMouseLeave={() => setTip(null)}
                onClick={() => onDrillDown?.(child.path)} />
            ) : (
              <FileShape cx={cx} cy={cy} r={r} color={color} borderColor={border}
                glow={tip?.name === child.name}
                handlers={{
                  onMouseEnter: (e) => setTip({ x: e.clientX, y: e.clientY, child }),
                  onMouseMove: (e) => setTip((t) => t ? { ...t, x: e.clientX, y: e.clientY } : null),
                  onMouseLeave: () => setTip(null),
                  onClick: () => onFileClick?.(child),
                  style: { cursor: onFileClick ? 'pointer' : 'default' },
                }} />
            )}
          </g>
        );
      })}

      {showLabels && (() => {
        const placed = [];
        const sorted = points
          .map((p, i) => ({ ...p, i }))
          .sort((a, b) => b.b - a.b);
        return sorted.map(({ child, x, y, b }) => {
          const cx = px(x), cy = py(y), r = br(b);
          const canDrill = !child.isFile && child.children?.length > 0;
          const labelY = canDrill ? cy - r - 4 : cy - r * 0.9 - 4;
          const fs = Math.min(LABEL_FONT_MAX, Math.max(LABEL_FONT_MIN, r / LABEL_FONT_DIVISOR));
          const estW = child.name.length * fs * LABEL_CHAR_WIDTH_FACTOR;
          const estH = fs + 2;
          const box = { x: cx - estW / 2, y: labelY - estH, w: estW, h: estH };
          const overlaps = placed.some((p) =>
            box.x < p.x + p.w && box.x + box.w > p.x &&
            box.y < p.y + p.h && box.y + box.h > p.y
          );
          if (overlaps) return null;
          if (placed.length < LABEL_PLACED_CAP) placed.push(box);
          return (
            <text
              key={'lbl-' + (child.path || child.name)}
              x={cx} y={labelY}
              textAnchor="middle" dominantBaseline="auto"
              style={{
                fontSize: fs,
                fontFamily: 'var(--font-sans)',
                fill: 'var(--color-text)',
                pointerEvents: 'none',
                fontWeight: canDrill ? 'var(--weight-semibold)' : 'var(--weight-normal)',
                opacity: entered ? 1 : 0,
                transition: 'opacity 0.2s ease',
              }}
            >
              {child.name}
            </text>
          );
        });
      })()}
    </>
  );
}

/* ── Sub-component: Tooltip overlay ── */

function MatrixTooltip({ tip }) {
  if (!tip) return null;
  const c = tip.child;
  const total = c.violations + c.compliance;
  const rate = total > 0 ? Math.round(c.compliance / total * 100) : 0;
  return (
    <div className="map-tooltip" style={{
      position: 'fixed',
      left: tip.x > window.innerWidth * TOOLTIP_FLIP_X_THRESHOLD ? undefined : tip.x + 12,
      right: tip.x > window.innerWidth * TOOLTIP_FLIP_X_THRESHOLD ? window.innerWidth - tip.x + 12 : undefined,
      top: tip.y > window.innerHeight * TOOLTIP_FLIP_Y_THRESHOLD ? undefined : tip.y - 12,
      bottom: tip.y > window.innerHeight * TOOLTIP_FLIP_Y_THRESHOLD ? window.innerHeight - tip.y + 12 : undefined,
    }}>
      <div className="map-tooltip-title">{c.path || c.name}</div>
      <div className="map-tooltip-row"><span>Violations</span><span>{c.violations}</span></div>
      <div className="map-tooltip-row"><span>Compliance</span><span>{c.compliance}</span></div>
      <div className="map-tooltip-row"><span>Health</span><span>{rate}%</span></div>
      {c.severity?.critical > 0 && <div className="map-tooltip-row" style={{ color: 'var(--color-sev-critical-text)' }}><span>Critical</span><span>{c.severity.critical}</span></div>}
      {c.severity?.major > 0 && <div className="map-tooltip-row" style={{ color: 'var(--color-sev-major-text)' }}><span>Major</span><span>{c.severity.major}</span></div>}
      {c.severity?.minor > 0 && <div className="map-tooltip-row" style={{ color: 'var(--color-sev-minor-text)' }}><span>Minor</span><span>{c.severity.minor}</span></div>}
    </div>
  );
}

/* ── Main orchestrator ── */

export default function RiskMatrixView({ node, onDrillDown, onFileClick, showLabels = true }) {
  const [tip, setTip] = useState(null);
  const [entered, setEntered] = useState(false);
  useEffect(() => { const t = setTimeout(() => setEntered(true), 50); return () => clearTimeout(t); }, []);

  const { points, px, py, br } = useBubbleLayout(node);

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: '100%', display: 'block' }}>
        <defs>
          <radialGradient id="riskDanger" cx="100%" cy="0%" r="100%">
            <stop offset="0%" stopColor="var(--color-sev-critical-text)" stopOpacity="0.12" />
            <stop offset="100%" stopColor="var(--color-sev-critical-text)" stopOpacity="0" />
          </radialGradient>
          <radialGradient id="riskSafe" cx="0%" cy="100%" r="100%">
            <stop offset="0%" stopColor="var(--color-compliance)" stopOpacity="0.10" />
            <stop offset="100%" stopColor="var(--color-compliance)" stopOpacity="0" />
          </radialGradient>
          <filter id="glow">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
        <rect x={PAD.l} y={PAD.t} width={PW} height={PH} fill="url(#riskDanger)" />
        <rect x={PAD.l} y={PAD.t} width={PW} height={PH} fill="url(#riskSafe)" />
        {[0.25, 0.5, 0.75].map((f) => (
          <g key={f} opacity={0.3}>
            <line x1={PAD.l} y1={PAD.t + PH * (1 - f)} x2={PAD.l + PW} y2={PAD.t + PH * (1 - f)} stroke="var(--color-border)" strokeWidth={0.5} />
            <line x1={PAD.l + PW * f} y1={PAD.t} x2={PAD.l + PW * f} y2={PAD.t + PH} stroke="var(--color-border)" strokeWidth={0.5} />
          </g>
        ))}
        <text x={PAD.l + PW - 8} y={PAD.t + 18} textAnchor="end" fontSize={10} fill="var(--color-sev-critical-text)" opacity={0.6} fontWeight="600" fontFamily="var(--font-sans)">Fix first</text>
        <text x={PAD.l + 8} y={PAD.t + PH - 8} textAnchor="start" fontSize={10} fill="var(--color-compliance)" opacity={0.6} fontWeight="600" fontFamily="var(--font-sans)">Low priority</text>
        <line x1={PAD.l} y1={PAD.t + PH} x2={PAD.l + PW} y2={PAD.t + PH} stroke="var(--color-border)" strokeWidth={1} />
        <line x1={PAD.l} y1={PAD.t} x2={PAD.l} y2={PAD.t + PH} stroke="var(--color-border)" strokeWidth={1} />
        <text x={PAD.l + PW / 2} y={H - 8} textAnchor="middle" fontSize={11} fill="var(--color-text-muted)" fontFamily="var(--font-sans)">Violations</text>
        <text x={14} y={PAD.t + PH / 2} textAnchor="middle" fontSize={11} fill="var(--color-text-muted)" fontFamily="var(--font-sans)" transform={`rotate(-90, 14, ${PAD.t + PH / 2})`}>Severity</text>
        <BubbleGroup points={points} px={px} py={py} br={br} entered={entered}
          showLabels={showLabels} tip={tip} setTip={setTip}
          onDrillDown={onDrillDown} onFileClick={onFileClick} />
      </svg>
      <MatrixTooltip tip={tip} />
    </div>
  );
}
