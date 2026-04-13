// File icon drawn at origin (centered on 0,0) with unit size ~1x1, scaled via transform.
// Use: <FileShape cx={x} cy={y} r={size} color={...} />
// The <g> wrapper handles positioning.
// When rendered inside a scaled parent <g>, pass parentScale to keep strokes crisp.

const BASE = 20; // internal coordinate size
const W = BASE * 0.7, H = BASE * 0.9;
const X = -W / 2, Y = -H / 2;
const FOLD = W * 0.25;
const RX = 1.5;
const LX1 = X + W * 0.2, LX2 = X + W * 0.8;
const LY1 = Y + H * 0.38, LY2 = Y + H * 0.54, LY3 = Y + H * 0.70;

const BODY = `M${X + RX},${Y} L${X + W - FOLD},${Y} L${X + W},${Y + FOLD} L${X + W},${Y + H - RX} Q${X + W},${Y + H} ${X + W - RX},${Y + H} L${X + RX},${Y + H} Q${X},${Y + H} ${X},${Y + H - RX} L${X},${Y + RX} Q${X},${Y} ${X + RX},${Y} Z`;
const FOLD_PATH = `M${X + W - FOLD},${Y} L${X + W - FOLD},${Y + FOLD} L${X + W},${Y + FOLD}`;

export default function FileShape({ cx, cy, r, color, borderColor, glow, handlers, transition = false, parentScale = 1 }) {
  const scale = r / (BASE / 2);
  // Compensate for both own scale and parent group scale to keep strokes at ~1px
  const totalScale = scale * parentScale;
  const stroke = borderColor || 'var(--color-border)';
  return (
    <g
      transform={`translate(${cx},${cy}) scale(${scale})`}
    >
      <path
        d={BODY}
        fill={color} fillOpacity={0.85} stroke={stroke} strokeWidth={0.8 / totalScale}
        filter={glow ? 'url(#glow)' : undefined}
        style={{ cursor: handlers?.onClick ? 'pointer' : 'default', transition: 'fill-opacity 0.2s ease' }}
        {...handlers}
      />
      <path d={FOLD_PATH}
        fill="none" stroke={stroke} strokeWidth={0.5 / totalScale} opacity={0.5} style={{ pointerEvents: 'none' }} />
      <line x1={LX1} y1={LY1} x2={LX2} y2={LY1} stroke="rgba(255,255,255,0.4)" strokeWidth={0.8 / totalScale} style={{ pointerEvents: 'none' }} />
      <line x1={LX1} y1={LY2} x2={LX2} y2={LY2} stroke="rgba(255,255,255,0.4)" strokeWidth={0.8 / totalScale} style={{ pointerEvents: 'none' }} />
      <line x1={LX1} y1={LY3} x2={LX2 * 0.85} y2={LY3} stroke="rgba(255,255,255,0.3)" strokeWidth={0.8 / totalScale} style={{ pointerEvents: 'none' }} />
    </g>
  );
}
