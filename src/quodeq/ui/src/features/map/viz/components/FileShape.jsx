import { activateOnKey } from '../../../../utils/a11y.js';

// File icon drawn at origin (centered on 0,0) with unit size ~1x1, scaled via transform.
// Use: <FileShape cx={x} cy={y} r={size} color={...} />
// The <g> wrapper handles positioning.
// When rendered inside a scaled parent <g>, pass parentScale to keep strokes crisp.

const BASE = 20; // internal coordinate size
// Page proportions and the dog-eared corner, as fractions of BASE.
const WIDTH_RATIO = 0.7, HEIGHT_RATIO = 0.9, FOLD_RATIO = 0.25;
// The three rule lines: how far in from each edge they start and end, and
// how far down the page each one sits. All fractions of the page box.
const LINE_LEFT_RATIO = 0.2, LINE_RIGHT_RATIO = 0.8;
const LINE_TOP_RATIO = 0.38, LINE_MID_RATIO = 0.54, LINE_BOTTOM_RATIO = 0.70;
// The bottom line is drawn short, as if the text ran out.
const LINE_BOTTOM_LENGTH_RATIO = 0.85;

const W = BASE * WIDTH_RATIO, H = BASE * HEIGHT_RATIO;
const X = -W / 2, Y = -H / 2;
const FOLD = W * FOLD_RATIO;
const RX = 1.5;
const LX1 = X + W * LINE_LEFT_RATIO, LX2 = X + W * LINE_RIGHT_RATIO;
const LY1 = Y + H * LINE_TOP_RATIO, LY2 = Y + H * LINE_MID_RATIO, LY3 = Y + H * LINE_BOTTOM_RATIO;

const BODY = `M${X + RX},${Y} L${X + W - FOLD},${Y} L${X + W},${Y + FOLD} L${X + W},${Y + H - RX} Q${X + W},${Y + H} ${X + W - RX},${Y + H} L${X + RX},${Y + H} Q${X},${Y + H} ${X},${Y + H - RX} L${X},${Y + RX} Q${X},${Y} ${X + RX},${Y} Z`;
const FOLD_PATH = `M${X + W - FOLD},${Y} L${X + W - FOLD},${Y + FOLD} L${X + W},${Y + FOLD}`;

// Stroke widths are divided by the total scale to stay ~1px on screen.
const BODY_STROKE_WIDTH_PX = 0.8;
const FOLD_STROKE_WIDTH_PX = 0.5;

const FILE_FILL_OPACITY = 0.85;
const FOLD_OPACITY = 0.5;
const LINE_OPACITY_PRIMARY = 0.4;
const LINE_OPACITY_SECONDARY = 0.3;

/** Button props for a clickable file body (none at all when it is static):
 * focusable, named, and activated by Enter or Space like its click. */
function buttonProps(handlers, ariaLabel) {
  if (!handlers?.onClick) return null;
  return { tabIndex: 0, role: 'button', 'aria-label': ariaLabel, onKeyDown: activateOnKey(handlers.onClick) };
}

export default function FileShape({ cx, cy, r, color, borderColor, glow, handlers, ariaLabel, parentScale = 1 }) {
  const scale = r / (BASE / 2);
  // Compensate for both own scale and parent group scale to keep strokes at ~1px
  const totalScale = scale * parentScale;
  const stroke = borderColor || 'var(--color-border)';
  return (
    <g
      transform={`translate(${cx},${cy}) scale(${scale})`}
    >
      <path
        className={handlers?.onClick ? 'viz-focusable' : undefined}
        d={BODY}
        fill={color} fillOpacity={FILE_FILL_OPACITY} stroke={stroke} strokeWidth={BODY_STROKE_WIDTH_PX / totalScale}
        filter={glow ? 'url(#glow)' : undefined}
        style={{ cursor: handlers?.onClick ? 'pointer' : 'default', transition: 'fill-opacity 0.2s ease' }}
        {...buttonProps(handlers, ariaLabel)}
        {...handlers}
      />
      <path d={FOLD_PATH}
        fill="none" stroke={stroke} strokeWidth={FOLD_STROKE_WIDTH_PX / totalScale} opacity={FOLD_OPACITY} style={{ pointerEvents: 'none' }} />
      <line x1={LX1} y1={LY1} x2={LX2} y2={LY1} stroke={`rgba(255,255,255,${LINE_OPACITY_PRIMARY})`} strokeWidth={BODY_STROKE_WIDTH_PX / totalScale} style={{ pointerEvents: 'none' }} />
      <line x1={LX1} y1={LY2} x2={LX2} y2={LY2} stroke={`rgba(255,255,255,${LINE_OPACITY_PRIMARY})`} strokeWidth={BODY_STROKE_WIDTH_PX / totalScale} style={{ pointerEvents: 'none' }} />
      <line x1={LX1} y1={LY3} x2={LX2 * LINE_BOTTOM_LENGTH_RATIO} y2={LY3} stroke={`rgba(255,255,255,${LINE_OPACITY_SECONDARY})`} strokeWidth={BODY_STROKE_WIDTH_PX / totalScale} style={{ pointerEvents: 'none' }} />
    </g>
  );
}
