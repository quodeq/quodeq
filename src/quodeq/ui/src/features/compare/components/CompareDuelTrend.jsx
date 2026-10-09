/**
 * CompareDuelTrend: both projects' overall score over one time axis, for
 * the head-to-head view. Each project is a smoothed trend line with its real
 * runs drawn faint behind it; the space between the two lines is tinted by
 * whoever leads; a dotted tail runs from each project's last run to today.
 * Hovering reads the REAL scores in force on that date, never smoothed ones.
 *
 * Drawn at the container's real pixel width (ResizeObserver), so the plot
 * fills its panel and the text never scales. Geometry lives in
 * duelTrendGeometry.js; this file only renders it.
 */
import { useLayoutEffect, useRef, useState } from 'react';
import { t, LOCALE } from '../../../strings/index.js';
import { scoreColorClass } from '../../../utils/formatters.js';
import { buildTrendGeometry, DUEL_SIDE, toPoints } from '../duelTrendGeometry.js';
import { gapClass, score1, signed1 } from './compareDuelShared.jsx';
import { roundOneDecimal } from '../../../utils/rounding.js';

const HEIGHT = 220;
const PAD = Object.freeze({ top: 16, right: 56, bottom: 8, left: 30 });
// Width before the first measurement (and in test environments without ResizeObserver).
const FALLBACK_WIDTH = 640;
// End labels closer than this get pushed apart.
const LABEL_MIN_GAP = 14;
const LABEL_NUDGE = LABEL_MIN_GAP / 2;
const LABEL_BASELINE = 4;
const TICK_X_OFFSET = 8;
const TICK_BASELINE = 3.5;
const WINDOW_LABEL_INSET = 4;
const WINDOW_LABEL_Y = 11;
const DOT_R = 3.5;
const HOVER_DOT_R = 4;
const TIP_OFFSET = 12;
const TIP_WIDTH = 190;

const shortDate = (ms) => new Date(ms).toLocaleDateString(LOCALE, { day: 'numeric', month: 'short' });

function useWidth(ready) {
  const ref = useRef(null);
  const [width, setWidth] = useState(FALLBACK_WIDTH);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width > 0) setWidth(Math.floor(entry.contentRect.width));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [ready]);
  return [ref, width];
}

/* End-of-line score labels, nudged apart when the lines finish close together. */
function endLabels(sides) {
  let ya = sides.a?.end.y;
  let yb = sides.b?.end.y;
  if (sides.a && sides.b && Math.abs(ya - yb) < LABEL_MIN_GAP) {
    const mid = (ya + yb) / 2;
    const aUp = sides.a.end.value >= sides.b.end.value;
    ya = mid + (aUp ? -LABEL_NUDGE : LABEL_NUDGE);
    yb = mid + (aUp ? LABEL_NUDGE : -LABEL_NUDGE);
  }
  return { a: ya, b: yb };
}

function Side({ side, geo, right }) {
  if (!geo) return null;
  return (
    <g>
      {geo.raw && <path className={`compare-duel-trend__raw compare-duel-trend__stroke--${side}`} d={geo.raw} />}
      {geo.trend && <path className={`compare-duel-trend__line compare-duel-trend__stroke--${side}`} d={geo.trend} />}
      <line className={`compare-duel-trend__tail compare-duel-trend__stroke--${side}`} x1={geo.tail.x1} x2={right} y1={geo.tail.y} y2={geo.tail.y} />
      {geo.single && <circle className={`compare-duel-trend__dot compare-duel-trend__dot--${side}`} cx={geo.single.x} cy={geo.single.y} r={DOT_R} />}
    </g>
  );
}

function Plot({ g, width, right, hoverX, onMove, onLeave, aName, bName }) {
  const labels = endLabels(g.sides);
  const hover = hoverX != null ? g.valueAt(hoverX) : null;
  return (
    <svg
      width={width}
      height={HEIGHT}
      className="compare-duel-trend__svg"
      role="img"
      aria-label={t('compare.trendChartAria', { a: aName, b: bName })}
      onMouseMove={onMove}
      onMouseLeave={onLeave}
    >
      <rect className="compare-duel-trend__window" x={g.window.x} y={PAD.top} width={g.window.width} height={HEIGHT - PAD.top - PAD.bottom} />
      <text className="compare-duel-trend__windowLabel" x={right - WINDOW_LABEL_INSET} y={PAD.top + WINDOW_LABEL_Y} textAnchor="end">{t('compare.duelTrendWindow')}</text>
      {g.yTicks.map((tk) => (
        <g key={tk.v}>
          <line className="compare-duel-trend__grid" x1={PAD.left} x2={right} y1={tk.y} y2={tk.y} />
          <text className="compare-duel-trend__tick" x={PAD.left - TICK_X_OFFSET} y={tk.y + TICK_BASELINE} textAnchor="end">{tk.v}</text>
        </g>
      ))}
      {g.gaps.map((p) => (
        <path key={p.d} className={`compare-duel-trend__gap compare-duel-trend__gap--${p.lead}${p.held ? ' compare-duel-trend__gap--held' : ''}`} d={p.d} />
      ))}
      <Side side={DUEL_SIDE.B} geo={g.sides.b} right={right} />
      <Side side={DUEL_SIDE.A} geo={g.sides.a} right={right} />
      {g.sides.a && <text className="compare-duel-trend__end compare-duel-trend__end--a" x={right + TICK_X_OFFSET} y={labels.a + LABEL_BASELINE}>{score1(g.sides.a.end.value)}</text>}
      {g.sides.b && <text className="compare-duel-trend__end compare-duel-trend__end--b" x={right + TICK_X_OFFSET} y={labels.b + LABEL_BASELINE}>{score1(g.sides.b.end.value)}</text>}
      {hover && (
        <g>
          <line className="compare-duel-trend__cross" x1={hoverX} x2={hoverX} y1={PAD.top} y2={HEIGHT - PAD.bottom} />
          {hover.a != null && <circle className="compare-duel-trend__dot compare-duel-trend__dot--a" cx={hoverX} cy={g.sides.a.yAt(hoverX) ?? g.yOf(hover.a)} r={HOVER_DOT_R} />}
          {hover.b != null && <circle className="compare-duel-trend__dot compare-duel-trend__dot--b" cx={hoverX} cy={g.sides.b.yAt(hoverX) ?? g.yOf(hover.b)} r={HOVER_DOT_R} />}
        </g>
      )}
    </svg>
  );
}

function HoverTip({ g, hoverX, width, aName, bName }) {
  const v = g.valueAt(hoverX);
  const gap = v.a != null && v.b != null ? roundOneDecimal(v.a - v.b) : null;
  return (
    <div className="compare-duel-trend__tip" style={{ left: Math.min(hoverX + TIP_OFFSET, width - TIP_WIDTH) }} aria-hidden="true">
      <span className="compare-duel-trend__tipDate">{shortDate(g.tAt(hoverX))}</span>
      <span><span className="compare-duel__swatch compare-duel__swatch--a" /> {aName} <b className={scoreColorClass(v.a)}>{score1(v.a)}</b></span>
      <span><span className="compare-duel__swatch compare-duel__swatch--b" /> {bName} <b className={scoreColorClass(v.b)}>{score1(v.b)}</b></span>
      {gap != null && (
        <span>{t('compare.duelTrendGap')} <span className={`compare-duel__gap ${gapClass(gap)}`}>{signed1(gap)}</span></span>
      )}
    </div>
  );
}

export default function CompareDuelTrend({ a, b, aName, bName, now = Date.now() }) {
  // Measured only while there is a chart to measure: an empty duel renders
  // nothing, and the observer attaches once runs arrive.
  const hasRuns = toPoints(a).length + toPoints(b).length > 0;
  const [ref, width] = useWidth(hasRuns);
  const [hoverX, setHoverX] = useState(null);
  const right = width - PAD.right;
  const box = { left: PAD.left, top: PAD.top, width: right - PAD.left, height: HEIGHT - PAD.top - PAD.bottom };
  const g = buildTrendGeometry({ a, b, box, now });
  if (!g) return null;

  const onMove = (e) => {
    const px = e.clientX - e.currentTarget.getBoundingClientRect().left;
    setHoverX(px >= box.left && px <= right ? px : null);
  };
  return (
    <div ref={ref} className="compare-duel-trend">
      <Plot g={g} width={width} right={right} hoverX={hoverX} onMove={onMove} onLeave={() => setHoverX(null)} aName={aName} bName={bName} />
      {/* The time axis in words, outside the role="img" svg so a screen
          reader still gets the span the chart covers (U-ACC-1). */}
      <div className="compare-duel-trend__dates">
        {g.xTicks.map((tk) => <span key={tk.t} style={{ left: tk.x }}>{shortDate(tk.t)}</span>)}
      </div>
      {hoverX != null && <HoverTip g={g} hoverX={hoverX} width={width} aName={aName} bName={bName} />}
    </div>
  );
}
