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
import { trendDomain, monotonePath } from '../compareTrendModel.js';

const W = 640;
const H = 240;
const PAD = { top: 12, right: 14, bottom: 8, left: 14 };

const shortDate = (ms) => new Date(ms).toLocaleDateString(LOCALE, { month: 'short', day: 'numeric' });

/* Lines stay clean: no per-point dots. A lone-point series still gets a
   visible dot (a dotless single point would vanish), and every point keeps
   an invisible, slightly larger circle as the tooltip hit target. */
function DuelTrendLine({ series, variant, x, y }) {
  if (series.length === 0) return null;
  return (
    <g>
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
}

/* The 30-day delta window, shaded so the numbers in the versus header
   visibly correspond to this slice of the chart. */
function DuelTrendWindow({ t0, t1, span }) {
  if (span <= 0) return null;
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
}

function DuelTrendGrid({ ticks, y }) {
  return ticks.map((v) => (
    <line
      key={v}
      className="compare-duel-trend__grid"
      x1={PAD.left}
      y1={y(v)}
      x2={W - PAD.right}
      y2={y(v)}
    />
  ));
}

/** The y-axis tick labels, an HTML overlay positioned to match the SVG grid. */
function DuelTrendAxis({ ticks, y }) {
  return (
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
  );
}

/**
 * @param {object} props
 * @param {{dateISO: string, value: number}[]} props.a - Oldest-first series.
 * @param {{dateISO: string, value: number}[]} props.b - Oldest-first series.
 */
export default function CompareDuelTrend({ a, b }) {
  const { t0, t1, v0, v1 } = trendDomain([a, b]);
  const span = t1 - t0;
  const x = (iso) => (span
    ? PAD.left + ((new Date(iso).getTime() - t0) / span) * (W - PAD.left - PAD.right)
    : W / 2);
  const y = (v) => PAD.top + (1 - (v - v0) / (v1 - v0)) * (H - PAD.top - PAD.bottom);

  const ticks = [];
  for (let v = v0; v <= v1; v += 1) ticks.push(v);

  return (
    <div className="compare-duel-trend">
      <div className="compare-duel-trend__plot">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" className="compare-duel-trend__svg">
          <DuelTrendWindow t0={t0} t1={t1} span={span} />
          <DuelTrendGrid ticks={ticks} y={y} />
          <DuelTrendLine key="b" series={b} variant="b" x={x} y={y} />
          <DuelTrendLine key="a" series={a} variant="a" x={x} y={y} />
        </svg>
        <DuelTrendAxis ticks={ticks} y={y} />
      </div>
      <div className="compare-duel-trend__dates" aria-hidden="true">
        <span>{shortDate(t0)}</span>
        {span > 0 && <span>{shortDate(t1)}</span>}
      </div>
    </div>
  );
}
