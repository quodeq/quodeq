/**
 * CompareDuelTrend — both projects' overall-score history on one time axis,
 * for the head-to-head view. Runs land at their real dates (not evenly
 * spaced), so unevenly paced projects still line up in time.
 *
 * Axis labels are HTML overlays rather than SVG text (the CompareRadar
 * pattern): the SVG scales with its container, and scaled text would drop
 * below the 11px floor. Colours come from CSS classes so theming stays in
 * compare.css.
 */
import { t, LOCALE } from '../../../strings/index.js';

const W = 640;
const H = 240;
const PAD = { top: 12, right: 14, bottom: 8, left: 14 };

function domain(series) {
  const times = series.flat().map((e) => new Date(e.dateISO).getTime());
  const values = series.flat().map((e) => e.value);
  // Pad the score range instead of pinning 0–10: real fleets live in a
  // narrow band and a full-scale axis would flatten both lines.
  const lo = Math.max(0, Math.floor(Math.min(...values) - 0.5));
  const hi = Math.min(10, Math.ceil(Math.max(...values) + 0.5));
  return {
    t0: Math.min(...times),
    t1: Math.max(...times),
    v0: lo,
    v1: hi > lo ? hi : lo + 1,
  };
}

const shortDate = (ms) => new Date(ms).toLocaleDateString(LOCALE, { month: 'short', day: 'numeric' });

/**
 * Monotone cubic (Fritsch-Carlson) path through the points: soft curves
 * that still pass through every value and never overshoot a peak or put a
 * wobble on a plateau — the same interpolation the Overview's line uses.
 */
function monotonePath(pts) {
  const n = pts.length;
  if (n < 2) return '';
  const seg = (p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`;
  if (n === 2) return `M${seg(pts[0])} L${seg(pts[1])}`;
  const dx = [];
  const slope = [];
  for (let i = 0; i < n - 1; i += 1) {
    dx.push(pts[i + 1][0] - pts[i][0]);
    slope.push((pts[i + 1][1] - pts[i][1]) / (dx[i] || 1));
  }
  const tangent = [slope[0]];
  for (let i = 1; i < n - 1; i += 1) {
    if (slope[i - 1] * slope[i] <= 0) {
      tangent.push(0);
    } else {
      const w1 = 2 * dx[i] + dx[i - 1];
      const w2 = dx[i] + 2 * dx[i - 1];
      tangent.push((w1 + w2) / (w1 / slope[i - 1] + w2 / slope[i]));
    }
  }
  tangent.push(slope[n - 2]);
  let d = `M${seg(pts[0])}`;
  for (let i = 0; i < n - 1; i += 1) {
    const h = dx[i] / 3;
    d += ` C${(pts[i][0] + h).toFixed(1)},${(pts[i][1] + h * tangent[i]).toFixed(1)}`
      + ` ${(pts[i + 1][0] - h).toFixed(1)},${(pts[i + 1][1] - h * tangent[i + 1]).toFixed(1)}`
      + ` ${seg(pts[i + 1])}`;
  }
  return d;
}

/**
 * @param {object} props
 * @param {{dateISO: string, value: number}[]} props.a - Oldest-first series.
 * @param {{dateISO: string, value: number}[]} props.b - Oldest-first series.
 */
export default function CompareDuelTrend({ a, b }) {
  const { t0, t1, v0, v1 } = domain([a, b]);
  const span = t1 - t0;
  const x = (iso) => (span
    ? PAD.left + ((new Date(iso).getTime() - t0) / span) * (W - PAD.left - PAD.right)
    : W / 2);
  const y = (v) => PAD.top + (1 - (v - v0) / (v1 - v0)) * (H - PAD.top - PAD.bottom);

  const ticks = [];
  for (let v = v0; v <= v1; v += 1) ticks.push(v);

  /* Lines stay clean: no per-point dots. A lone-point series still gets a
     visible dot (a dotless single point would vanish), and every point
     keeps an invisible, slightly larger circle as the tooltip hit
     target. */
  const line = (series, variant) => series.length > 0 && (
    <g key={variant}>
      {series.length > 1 ? (
        <path
          className={`compare-duel-trend__line compare-duel-trend__line--${variant}`}
          d={monotonePath(series.map((e) => [x(e.dateISO), y(e.value)]))}
        />
      ) : (
        <circle
          className={`compare-duel-trend__dot compare-duel-trend__dot--${variant}`}
          cx={x(series[0].dateISO).toFixed(1)}
          cy={y(series[0].value).toFixed(1)}
          r="4"
        />
      )}
      {series.map((e) => (
        <circle
          key={e.dateISO}
          className="compare-duel-trend__hit"
          cx={x(e.dateISO).toFixed(1)}
          cy={y(e.value).toFixed(1)}
          r="7"
        >
          <title>
            {t('compare.duelPointTip', { date: shortDate(Date.parse(e.dateISO)), score: e.value.toFixed(1) })}
          </title>
        </circle>
      ))}
    </g>
  );

  return (
    <div className="compare-duel-trend">
      <div className="compare-duel-trend__plot">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" className="compare-duel-trend__svg">
          {/* The 30-day delta window, shaded so the numbers in the versus
              header visibly correspond to this slice of the chart. */}
          {span > 0 && (() => {
            const windowStart = Math.max(t0, t1 - 30 * 86400000);
            const xw = PAD.left + ((windowStart - t0) / span) * (W - PAD.left - PAD.right);
            return (
              <rect
                className="compare-duel-trend__window"
                x={xw.toFixed(1)}
                y={PAD.top}
                width={(W - PAD.right - xw).toFixed(1)}
                height={H - PAD.top - PAD.bottom}
              />
            );
          })()}
          {ticks.map((v) => (
            <line
              key={v}
              className="compare-duel-trend__grid"
              x1={PAD.left}
              y1={y(v)}
              x2={W - PAD.right}
              y2={y(v)}
            />
          ))}
          {line(b, 'b')}
          {line(a, 'a')}
        </svg>
        <div className="compare-duel-trend__ticks" aria-hidden="true">
          {ticks.map((v) => (
            <span
              key={v}
              className="compare-duel-trend__tick"
              style={{ top: `${(y(v) / H) * 100}%` }}
            >
              {v}
            </span>
          ))}
        </div>
      </div>
      <div className="compare-duel-trend__dates" aria-hidden="true">
        <span>{shortDate(t0)}</span>
        {span > 0 && <span>{shortDate(t1)}</span>}
      </div>
    </div>
  );
}
