/**
 * CompareRadar — small SVG radar for the dimension drill-down. Plots one
 * polygon per series over the dimension's principle axes on a 0–10 scale.
 * Purely presentational; colours come from CSS classes so theming stays in
 * compare.css.
 */
import { t } from '../../../strings/index.js';
import { SCORE_SCALE_MAX } from '../../../constants.js';

const W = 440;
const H = 320;
const CX = W / 2;
const CY = 156;
const R = 112;
const RING_QUARTER = 0.25;
const RING_HALF = 0.5;
const RING_THREE_QUARTERS = 0.75;
const RINGS = [RING_QUARTER, RING_HALF, RING_THREE_QUARTERS, 1];

// Angle math: start at 12 o'clock and sweep a full turn across the axes,
// converting degrees to radians (Math.PI / DEG_TO_RAD_DIVISOR).
const START_ANGLE_DEG = -90;
const FULL_CIRCLE_DEG = 360;
const DEG_TO_RAD_DIVISOR = 180;
// A zero-score axis still plots a small distance from center instead of
// collapsing the polygon to a point.
const MIN_POINT_FRACTION = 0.06;
// Fewer than 3 axes cannot form a polygon.
const MIN_RADAR_AXES = 3;
// Labels sit further out than the polygon points themselves.
const LABEL_RADIUS_MULTIPLIER = 1.3;

function point(index, count, frac) {
  const angle = ((START_ANGLE_DEG + (index * FULL_CIRCLE_DEG) / count) * Math.PI) / DEG_TO_RAD_DIVISOR;
  return [CX + Math.cos(angle) * R * frac, CY + Math.sin(angle) * R * frac];
}

function polygonPoints(values, count) {
  return values
    .map((v, i) => point(i, count, Math.max(MIN_POINT_FRACTION, (v ?? 0) / SCORE_SCALE_MAX)).map((n) => n.toFixed(1)).join(','))
    .join(' ');
}

/**
 * @param {object} props
 * @param {{label: string, value: number|null}[]} props.axes
 * @param {{values: (number|null)[], variant: string, focused?: boolean}[]} props.series
 *   variant becomes the class suffix: compare-radar__poly--<variant>;
 *   focused adds is-focused, recoloring the polygon to the focus style.
 */
export default function CompareRadar({ axes, series }) {
  const n = axes.length;
  if (n < MIN_RADAR_AXES) return null;
  return (
    <div className="compare-radar">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={t('compare.radarChartAria')}
        className="compare-radar__svg"
      >
        {RINGS.map((f) => (
          <polygon
            key={f}
            className="compare-radar__ring"
            points={axes.map((_, i) => point(i, n, f).map((x) => x.toFixed(1)).join(',')).join(' ')}
          />
        ))}
        {axes.map((_, i) => {
          const [x, y] = point(i, n, 1);
          return <line key={i} className="compare-radar__axis" x1={CX} y1={CY} x2={x} y2={y} />;
        })}
        {series.map((s) => (
          <polygon
            key={s.variant}
            className={`compare-radar__poly compare-radar__poly--${s.variant}${s.focused ? ' is-focused' : ''}`}
            points={polygonPoints(s.values, n)}
          />
        ))}
      </svg>
      {/* Not aria-hidden: these overlays carry the only text form of the
          chart's data, and the svg above is a role="img" whose contents are
          pruned, so hiding them left the scores unreachable (U-ACC-2). */}
      <div className="compare-radar__labels">
        {axes.map((axis, i) => {
          const [x, y] = point(i, n, LABEL_RADIUS_MULTIPLIER);
          return (
            <div
              key={axis.label}
              className="compare-radar__label"
              style={{ left: `${(x / W) * 100}%`, top: `${(y / H) * 100}%` }}
            >
              <span className="compare-radar__labelName">{axis.label}</span>
              {axis.value != null && (
                <span className="compare-radar__labelScore">{axis.value.toFixed(1)}</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
