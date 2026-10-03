import { activateOnKey } from '../../../../utils/a11y.js';
import {
  FILE_SHAPE_BASE as BASE, FILE_X, FILE_Y, FILE_W, FILE_H, FILE_FOLD, FILE_CORNER_RX,
  FILE_BODY_STROKE_PX as BODY_STROKE_WIDTH_PX, FILE_FOLD_STROKE_PX as FOLD_STROKE_WIDTH_PX,
  FILE_FILL_OPACITY, FILE_FOLD_OPACITY as FOLD_OPACITY, FILE_RULE_LINES, ruleLineColor,
} from '../core/fileShapeGeometry.js';

// File icon drawn at origin (centered on 0,0) with unit size ~1x1, scaled via transform.
// Use: <FileShape cx={x} cy={y} r={size} color={...} />
// The <g> wrapper handles positioning.
// When rendered inside a scaled parent <g>, pass parentScale to keep strokes crisp.

const X = FILE_X, Y = FILE_Y, W = FILE_W, H = FILE_H, FOLD = FILE_FOLD, RX = FILE_CORNER_RX;

const BODY = `M${X + RX},${Y} L${X + W - FOLD},${Y} L${X + W},${Y + FOLD} L${X + W},${Y + H - RX} Q${X + W},${Y + H} ${X + W - RX},${Y + H} L${X + RX},${Y + H} Q${X},${Y + H} ${X},${Y + H - RX} L${X},${Y + RX} Q${X},${Y} ${X + RX},${Y} Z`;
const FOLD_PATH = `M${X + W - FOLD},${Y} L${X + W - FOLD},${Y + FOLD} L${X + W},${Y + FOLD}`;

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
      {FILE_RULE_LINES.map(([x1, y, x2, opacity]) => (
        <line key={y} x1={x1} y1={y} x2={x2} y2={y} stroke={ruleLineColor(opacity)} strokeWidth={BODY_STROKE_WIDTH_PX / totalScale} style={{ pointerEvents: 'none' }} />
      ))}
    </g>
  );
}
