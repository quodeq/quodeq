/**
 * Pixel geometry for CompareDuelTrend, kept pure so it is testable without a
 * browser: both projects' smoothed trend lines, their real runs as faint
 * steps, the fill between the lines tinted by who leads, and the dotted
 * "no scan since" tails. Nothing here renders.
 *
 * The trend is time-weighted smoothing (smoothSeries) drawn as the monotone
 * curve through it. The fill samples that same curve (monotoneAt), so it
 * hugs the drawn lines whatever their shape. Past a project's last run its
 * value is held, and past the newest run of either project the fill is
 * marked `held`: the lead there is assumed, not measured.
 */
import { monotoneAt, monotonePath, smoothSeries, stepValueAt } from './compareTrendModel.js';
import { scoreDomain } from '../../components/scoreChartHelpers.js';
import { MS_PER_DAY } from '../../utils/time.js';
import { DELTA_WINDOW_DAYS } from './compareModel.js';

// A run's pull on the trend halves in about five days.
const SMOOTHING_DAYS = 7;
// Sample the curves every SAMPLE_PX pixels for the fill.
const SAMPLE_PX = 2;
// Roughly one date label per this many pixels, between MIN and MAX labels.
const X_LABEL_PX = 120;
const MIN_X_LABELS = 2;
const MAX_X_LABELS = 6;
// Value spans wider than this get a tick every other point.
const WIDE_SPAN = 5;
const SIDES = ['a', 'b'];

export const DUEL_SIDE = Object.freeze({ A: 'a', B: 'b' });

export function toPoints(series) {
  return series
    .map((e) => ({ t: Date.parse(e.dateISO), v: e.value }))
    .filter((p) => Number.isFinite(p.t) && p.v != null)
    .sort((p, q) => p.t - q.t);
}

function scales(points, now, box) {
  const all = points.a.concat(points.b);
  const t0 = Math.min(...all.map((p) => p.t));
  const t1 = Math.max(now, ...all.map((p) => p.t));
  const [v0, v1] = scoreDomain(all.map((p) => p.v));
  const x = (t) => box.left + ((t - t0) / (t1 - t0 || 1)) * box.width;
  const y = (v) => box.top + (1 - (v - v0) / (v1 - v0 || 1)) * box.height;
  return { t0, t1, v0, v1, x, y };
}

function stepPath(pts, x, y) {
  if (!pts.length) return '';
  let d = `M${x(pts[0].t).toFixed(1)},${y(pts[0].v).toFixed(1)}`;
  for (const p of pts.slice(1)) d += `H${x(p.t).toFixed(1)}V${y(p.v).toFixed(1)}`;
  return d;
}

/* One side: px points of the smoothed curve, plus what the chart draws. */
function sideGeometry(pts, sc) {
  if (!pts.length) return null;
  const smooth = smoothSeries(pts, SMOOTHING_DAYS * MS_PER_DAY).map((p) => [sc.x(p.t), sc.y(p.v)]);
  const last = pts[pts.length - 1];
  const lastX = sc.x(last.t);
  return {
    smooth,
    trend: pts.length > 1 ? monotonePath(smooth) : '',
    raw: pts.length > 1 ? stepPath(pts, sc.x, sc.y) : '',
    single: pts.length === 1 ? { x: lastX, y: sc.y(last.v) } : null,
    tail: { x1: lastX, x2: sc.x(sc.t1), y: sc.y(last.v) },
    end: { value: last.v, y: sc.y(last.v) },
    // y of the drawn line at px x: the curve inside its span, held after it.
    yAt: (px) => (px > lastX ? sc.y(last.v) : monotoneAt(smooth, px)),
  };
}

/* Fill pieces between the two curves, split wherever the leader or the
   held state changes. In SVG y grows downward: a smaller y is the higher score. */
function gapPieces(ga, gb, from, to, heldFrom) {
  const pieces = [];
  let cur = null;
  let prev = null;
  // Sample every SAMPLE_PX, always ending exactly on `to`.
  const xs = [];
  for (let px = from; px < to; px += SAMPLE_PX) xs.push(px);
  xs.push(to);
  for (const at of xs) {
    const ya = ga.yAt(at);
    const yb = gb.yAt(at);
    if (ya == null || yb == null || ya === yb) { cur = null; prev = null; continue; }
    const lead = ya < yb ? DUEL_SIDE.A : DUEL_SIDE.B;
    const held = at > heldFrom;
    if (!cur || cur.lead !== lead || cur.held !== held) {
      cur = { lead, held, top: prev ? [prev.a] : [], bottom: prev ? [prev.b] : [] };
      pieces.push(cur);
    }
    prev = { a: [at, ya], b: [at, yb] };
    cur.top.push(prev.a);
    cur.bottom.push(prev.b);
  }
  const fmt = (q) => `${q[0].toFixed(1)},${q[1].toFixed(1)}`;
  return pieces
    .filter((p) => p.top.length > 1)
    .map((p) => ({ lead: p.lead, held: p.held, d: `M${p.top.map(fmt).join('L')}L${[...p.bottom].reverse().map(fmt).join('L')}Z` }));
}

function ticks(sc, box) {
  const yTicks = [];
  const step = sc.v1 - sc.v0 > WIDE_SPAN ? 2 : 1;
  for (let v = Math.ceil(sc.v0); v <= sc.v1; v += step) yTicks.push({ v, y: sc.y(v) });
  const n = Math.max(MIN_X_LABELS, Math.min(MAX_X_LABELS, Math.floor(box.width / X_LABEL_PX)));
  const xTicks = Array.from({ length: n }, (_, i) => {
    const t = sc.t0 + ((sc.t1 - sc.t0) * i) / (n - 1);
    return { t, x: sc.x(t) };
  });
  return { yTicks, xTicks };
}

/**
 * Everything the chart draws, in px, for a plot box {left, top, width,
 * height}. Returns null when there is nothing to draw (no parseable runs).
 * `valueAt(px)` reports the REAL scores in force at a px x: hover shows
 * what the runs scored, never a smoothed value.
 */
export function buildTrendGeometry({ a, b, box, now }) {
  const points = { a: toPoints(a), b: toPoints(b) };
  if (points.a.length + points.b.length === 0) return null;
  const sc = scales(points, now, box);
  const sides = { a: sideGeometry(points.a, sc), b: sideGeometry(points.b, sc) };
  let gaps = [];
  if (sides.a && sides.b) {
    const from = Math.max(sc.x(points.a[0].t), sc.x(points.b[0].t));
    const newest = Math.max(points.a.at(-1).t, points.b.at(-1).t);
    gaps = gapPieces(sides.a, sides.b, Math.ceil(from), box.left + box.width, sc.x(newest));
  }
  const windowX = sc.x(Math.max(sc.t0, sc.t1 - DELTA_WINDOW_DAYS * MS_PER_DAY));
  const tAt = (px) => sc.t0 + ((px - box.left) / box.width) * (sc.t1 - sc.t0);
  return {
    ...ticks(sc, box),
    sides,
    gaps,
    window: { x: windowX, width: box.left + box.width - windowX },
    tAt,
    valueAt: (px) => {
      const t = tAt(px);
      return Object.fromEntries(SIDES.map((s) => [s, stepValueAt(points[s], t)]));
    },
    yOf: sc.y,
  };
}
