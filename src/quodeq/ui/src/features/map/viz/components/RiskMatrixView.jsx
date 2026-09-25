import { useMemo, useState, useEffect } from 'react';
import { nodeColor, nodeBorderColor } from '../core/mapColors.js';
import { riskPoint } from '../core/riskScore.js';
import FileShape from './FileShape.jsx';
import { activateOnKey } from '../../../../utils/a11y.js';
import { t } from '../../../../strings/index.js';
import { riskBubbleKey } from './riskBubbleName.js';
import { LABEL_GAP_PX } from './viewLabels.js';
import { PERCENT } from '../../../../constants.js';

const W = 600, H = 420, PAD = { l: 55, r: 25, t: 35, b: 55 };
const PW = W - PAD.l - PAD.r, PH = H - PAD.t - PAD.b;

const BUBBLE_RADIUS_MIN = 3;
const BUBBLE_RADIUS_RANGE = 8;
const LABEL_FONT_MAX = 11;
const LABEL_FONT_MIN = 8;
const LABEL_FONT_DIVISOR = 3;
const LABEL_CHAR_WIDTH_FACTOR = 0.55;
const LABEL_PLACED_CAP = 100;
const AXIS_SCALE_MARGIN = 1.15;
const ENTRANCE_DELAY_MS = 50;
const TOOLTIP_FLIP_X_THRESHOLD = 0.65;
const TOOLTIP_FLIP_Y_THRESHOLD = 0.75;
const TOOLTIP_OFFSET_PX = 12;
// The pulsing ring that marks a bubble carrying critical violations: its
// resting radius, and the radius the pulse swells out to.
const CRITICAL_RING_PAD_PX = 4;
const CRITICAL_RING_PULSE_PAD_PX = 8;
// A file is drawn as a page glyph rather than a circle, so its visual top
// sits inside the nominal radius and the label follows it in.
const FILE_LABEL_RADIUS_FRACTION = 0.9;
// The plot is split into this many bands on each axis; the gridlines are
// the boundaries between them, as fractions of the axis.
const GRIDLINE_BANDS = 4;
const GRIDLINE_FRACTIONS = Object.freeze(
  Array.from({ length: GRIDLINE_BANDS - 1 }, (_, i) => (i + 1) / GRIDLINE_BANDS),
);
// The two corner captions ("fix first" / "low priority"): how far in from
// the plot's edges they sit, and their type.
const QUADRANT_LABEL_INSET_PX = 8;
const QUADRANT_LABEL_TOP_PX = 18;
const QUADRANT_LABEL_FONT_PX = 10;
// The axis titles: their type, and the gap below the plot / in from the
// left edge that they are centred in.
const AXIS_TITLE_FONT_PX = 11;
const AXIS_TITLE_BOTTOM_GAP_PX = 8;
const AXIS_TITLE_LEFT_PX = 14;

/* ── Hook: bubble positioning & collision detection ── */

function useBubbleLayout(node) {
  const items = useMemo(() => (node.children?.length > 0 ? node.children : [node]), [node]);

  const { points, maxX, maxY, maxB } = useMemo(() => {
    const pts = items.map((c) => ({
      child: c,
      ...riskPoint(c),
      color: nodeColor(c, 'violations'),
      border: nodeBorderColor(c, 'violations'),
      hasCritical: (c.severity?.critical || 0) > 0,
    }));
    return {
      points: pts,
      maxX: Math.max(1, ...pts.map((p) => p.x)) * AXIS_SCALE_MARGIN,
      maxY: Math.max(1, ...pts.map((p) => p.y)) * AXIS_SCALE_MARGIN,
      maxB: Math.max(1, ...pts.map((p) => p.b)),
    };
  }, [items]);

  const log = (v, max) => max > 0 ? Math.log1p(v) / Math.log1p(max) : 0;
  const px = (x) => PAD.l + log(x, maxX) * PW;
  const py = (y) => PAD.t + PH - log(y, maxY) * PH;
  const br = (b) => BUBBLE_RADIUS_MIN + (b / maxB) * BUBBLE_RADIUS_RANGE;

  return { points, px, py, br };
}

/* ── Sub-component: one bubble's circle/shape + critical-alert ring ── */

function BubbleNode({ point, px, py, br, entered, tip, setTip, onDrillDown, onFileClick }) {
  const { child, x, y, b, color, border, hasCritical } = point;
  const cx = px(x), cy = py(y), r = br(b);
  const canDrill = !child.isFile && child.children?.length > 0;
  return (
    <g style={{ opacity: entered ? 1 : 0, transition: 'opacity 0.2s ease' }}>
      {hasCritical && <circle cx={cx} cy={cy} r={r + CRITICAL_RING_PAD_PX} fill="none" stroke={color} strokeWidth={1} opacity={0.3}>
        <animate attributeName="r" values={`${r + 2};${r + CRITICAL_RING_PULSE_PAD_PX};${r + 2}`} dur="2s" repeatCount="indefinite" />
        <animate attributeName="opacity" values="0.3;0.1;0.3" dur="2s" repeatCount="indefinite" />
      </circle>}
      {canDrill ? (
        <circle className="viz-focusable" cx={cx} cy={cy} r={r} fill={color} fillOpacity={0.85}
          stroke={border} strokeWidth={1}
          filter={tip?.name === child.name ? 'url(#glow)' : undefined}
          style={{ cursor: 'pointer', transition: 'fill-opacity 0.2s ease' }}
          tabIndex={0}
          role="button"
          aria-label={child.name || child.path}
          onMouseEnter={(e) => setTip({ x: e.clientX, y: e.clientY, child })}
          onMouseMove={(e) => setTip((prev) => prev ? { ...prev, x: e.clientX, y: e.clientY } : null)}
          onMouseLeave={() => setTip(null)}
          onClick={() => onDrillDown?.(child.path)}
          onKeyDown={activateOnKey(() => onDrillDown?.(child.path))} />
      ) : (
        <FileShape cx={cx} cy={cy} r={r} color={color} borderColor={border}
          glow={tip?.name === child.name}
          ariaLabel={t(riskBubbleKey(child.violations), { file: child.name || child.path, count: child.violations || 0 })}
          handlers={{
            onMouseEnter: (e) => setTip({ x: e.clientX, y: e.clientY, child }),
            onMouseMove: (e) => setTip((prev) => prev ? { ...prev, x: e.clientX, y: e.clientY } : null),
            onMouseLeave: () => setTip(null),
            onClick: () => onFileClick?.(child),
            style: { cursor: onFileClick ? 'pointer' : 'default' },
          }} />
      )}
    </g>
  );
}

/* ── Sub-component: bubble name labels, with collision avoidance ── */

function BubbleLabels({ points, px, py, br, entered }) {
  const placed = [];
  const sorted = points
    .map((p, i) => ({ ...p, i }))
    .sort((a, b) => b.b - a.b);
  return sorted.map(({ child, x, y, b }) => {
    const cx = px(x), cy = py(y), r = br(b);
    const canDrill = !child.isFile && child.children?.length > 0;
    const labelY = canDrill ? cy - r - LABEL_GAP_PX : cy - r * FILE_LABEL_RADIUS_FRACTION - LABEL_GAP_PX;
    const fs = Math.min(LABEL_FONT_MAX, Math.max(LABEL_FONT_MIN, r / LABEL_FONT_DIVISOR));
    const estW = (child.name || '').length * fs * LABEL_CHAR_WIDTH_FACTOR;
    const estH = fs + 2;
    const box = { x: cx - estW / 2, y: labelY - estH, w: estW, h: estH };
    // O(n^2) collision check is acceptable here: LABEL_PLACED_CAP limits
    // placed labels to 100 entries, so worst case is ~5,000 comparisons.
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
}

/* ── Sub-component: SVG bubble circles & labels ── */

function BubbleGroup({ points, px, py, br, entered, showLabels, tip, setTip, onDrillDown, onFileClick }) {
  return (
    <>
      {points.map((point) => (
        <BubbleNode
          key={point.child.path || point.child.name}
          point={point} px={px} py={py} br={br} entered={entered}
          tip={tip} setTip={setTip} onDrillDown={onDrillDown} onFileClick={onFileClick}
        />
      ))}
      {showLabels && <BubbleLabels points={points} px={px} py={py} br={br} entered={entered} />}
    </>
  );
}

/* ── Sub-component: Tooltip overlay ── */

function MatrixTooltip({ tip }) {
  if (!tip) return null;
  const c = tip.child;
  const total = c.violations + c.compliance;
  const rate = total > 0 ? Math.round(c.compliance / total * PERCENT) : 0;
  return (
    <div className="map-tooltip" style={{
      position: 'fixed',
      left: tip.x > window.innerWidth * TOOLTIP_FLIP_X_THRESHOLD ? undefined : tip.x + TOOLTIP_OFFSET_PX,
      right: tip.x > window.innerWidth * TOOLTIP_FLIP_X_THRESHOLD ? window.innerWidth - tip.x + TOOLTIP_OFFSET_PX : undefined,
      top: tip.y > window.innerHeight * TOOLTIP_FLIP_Y_THRESHOLD ? undefined : tip.y - TOOLTIP_OFFSET_PX,
      bottom: tip.y > window.innerHeight * TOOLTIP_FLIP_Y_THRESHOLD ? window.innerHeight - tip.y + TOOLTIP_OFFSET_PX : undefined,
    }}>
      <div className="map-tooltip-title">{c.path || c.name}</div>
      <div className="map-tooltip-row"><span>{t('map.violations')}</span><span>{c.violations}</span></div>
      <div className="map-tooltip-row"><span>{t('map.compliance')}</span><span>{c.compliance}</span></div>
      <div className="map-tooltip-row"><span>{t('map.health')}</span><span>{rate}%</span></div>
      {c.severity?.critical > 0 && <div className="map-tooltip-row" style={{ color: 'var(--color-sev-critical-text)' }}><span>{t('map.critical')}</span><span>{c.severity.critical}</span></div>}
      {c.severity?.major > 0 && <div className="map-tooltip-row" style={{ color: 'var(--color-sev-major-text)' }}><span>{t('map.major')}</span><span>{c.severity.major}</span></div>}
      {c.severity?.minor > 0 && <div className="map-tooltip-row" style={{ color: 'var(--color-sev-minor-text)' }}><span>{t('map.minor')}</span><span>{c.severity.minor}</span></div>}
    </div>
  );
}

/* ── Main orchestrator ── */

export default function RiskMatrixView({ node, onDrillDown, onFileClick, showLabels = true }) {
  const [tip, setTip] = useState(null);
  const [entered, setEntered] = useState(false);
  useEffect(() => { const timer = setTimeout(() => setEntered(true), ENTRANCE_DELAY_MS); return () => clearTimeout(timer); }, []);

  const { points, px, py, br } = useBubbleLayout(node);

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: '100%', display: 'block' }} aria-label={t('map.riskMatrixAria')}>
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
        {GRIDLINE_FRACTIONS.map((f) => (
          <g key={f} opacity={0.3}>
            <line x1={PAD.l} y1={PAD.t + PH * (1 - f)} x2={PAD.l + PW} y2={PAD.t + PH * (1 - f)} stroke="var(--color-border)" strokeWidth={0.5} />
            <line x1={PAD.l + PW * f} y1={PAD.t} x2={PAD.l + PW * f} y2={PAD.t + PH} stroke="var(--color-border)" strokeWidth={0.5} />
          </g>
        ))}
        <text x={PAD.l + PW - QUADRANT_LABEL_INSET_PX} y={PAD.t + QUADRANT_LABEL_TOP_PX} textAnchor="end" fontSize={QUADRANT_LABEL_FONT_PX} fill="var(--color-sev-critical-text)" opacity={0.6} fontWeight="600" fontFamily="var(--font-sans)">{t('map.fixFirst')}</text>
        <text x={PAD.l + QUADRANT_LABEL_INSET_PX} y={PAD.t + PH - QUADRANT_LABEL_INSET_PX} textAnchor="start" fontSize={QUADRANT_LABEL_FONT_PX} fill="var(--color-compliance)" opacity={0.6} fontWeight="600" fontFamily="var(--font-sans)">{t('map.lowPriority')}</text>
        <line x1={PAD.l} y1={PAD.t + PH} x2={PAD.l + PW} y2={PAD.t + PH} stroke="var(--color-border)" strokeWidth={1} />
        <line x1={PAD.l} y1={PAD.t} x2={PAD.l} y2={PAD.t + PH} stroke="var(--color-border)" strokeWidth={1} />
        <text x={PAD.l + PW / 2} y={H - AXIS_TITLE_BOTTOM_GAP_PX} textAnchor="middle" fontSize={AXIS_TITLE_FONT_PX} fill="var(--color-text-muted)" fontFamily="var(--font-sans)">{t('map.violations')}</text>
        <text x={AXIS_TITLE_LEFT_PX} y={PAD.t + PH / 2} textAnchor="middle" fontSize={AXIS_TITLE_FONT_PX} fill="var(--color-text-muted)" fontFamily="var(--font-sans)" transform={`rotate(-90, ${AXIS_TITLE_LEFT_PX}, ${PAD.t + PH / 2})`}>{t('map.severity')}</text>
        <BubbleGroup points={points} px={px} py={py} br={br} entered={entered}
          showLabels={showLabels} tip={tip} setTip={setTip}
          onDrillDown={onDrillDown} onFileClick={onFileClick} />
      </svg>
      <MatrixTooltip tip={tip} />
    </div>
  );
}
