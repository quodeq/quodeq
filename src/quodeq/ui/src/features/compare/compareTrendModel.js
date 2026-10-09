/**
 * Pure curve maths for the duel trend (duelTrendGeometry.js): the monotone
 * cubic through a set of points (drawn and sampled), time-weighted
 * smoothing, and step lookup. Nothing here fetches or renders.
 */

/**
 * Monotone cubic (Fritsch-Carlson) path through the points: soft curves
 * that still pass through every value and never overshoot a peak or put a
 * wobble on a plateau — the same interpolation the Overview's line uses.
 */
// Standard Hermite-to-Bezier conversion: each segment's cubic control points
// sit a third of the way along it.
const CONTROL_POINT_FRACTION_DIVISOR = 3;
// The 3 in the cubic Hermite basis (2u^3 - 3u^2 + 1 and -2u^3 + 3u^2).
const HERMITE_THREE = 3;

/**
 * Per-point tangents for the monotone cubic through `pts` ([x, y] pairs,
 * x ascending): a weighted harmonic mean of the neighbouring slopes, and a
 * flat tangent at every local peak or valley so the curve never overshoots.
 * Shared by monotonePath (drawing) and monotoneAt (sampling), so a fill
 * computed from samples hugs the drawn line exactly.
 */
export function monotoneTangents(pts) {
  const n = pts.length;
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
  return { dx, tangent };
}

export function monotonePath(pts) {
  const n = pts.length;
  if (n < 2) return '';
  const seg = (p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`;
  if (n === 2) return `M${seg(pts[0])} L${seg(pts[1])}`;
  const { dx, tangent } = monotoneTangents(pts);
  const parts = [`M${seg(pts[0])}`];
  for (let i = 0; i < n - 1; i += 1) {
    const h = dx[i] / CONTROL_POINT_FRACTION_DIVISOR;
    parts.push(
      ` C${(pts[i][0] + h).toFixed(1)},${(pts[i][1] + h * tangent[i]).toFixed(1)}`
      + ` ${(pts[i + 1][0] - h).toFixed(1)},${(pts[i + 1][1] - h * tangent[i + 1]).toFixed(1)}`
      + ` ${seg(pts[i + 1])}`,
    );
  }
  return parts.join('');
}

/**
 * The y of monotonePath's curve at `x` (Hermite form of the same cubic), or
 * null outside the points' x span. Two points are a straight segment, the
 * same as the path draws them.
 */
export function monotoneAt(pts, x) {
  const n = pts.length;
  if (n === 0 || x < pts[0][0] || x > pts[n - 1][0]) return null;
  if (n === 1) return pts[0][1];
  let i = 0;
  while (i < n - 2 && x > pts[i + 1][0]) i += 1;
  const h = pts[i + 1][0] - pts[i][0];
  if (!h) return pts[i + 1][1];
  const u = (x - pts[i][0]) / h;
  if (n === 2) return pts[0][1] + u * (pts[1][1] - pts[0][1]);
  const { tangent } = monotoneTangents(pts);
  const u2 = u * u;
  const u3 = u2 * u;
  // Cubic Hermite basis functions (h00, h10, h01, h11).
  const h00 = 2 * u3 - HERMITE_THREE * u2 + 1;
  const h10 = u3 - 2 * u2 + u;
  const h01 = HERMITE_THREE * u2 - 2 * u3;
  const h11 = u3 - u2;
  return h00 * pts[i][1] + h10 * h * tangent[i] + h01 * pts[i + 1][1] + h11 * h * tangent[i + 1];
}

/**
 * Time-weighted exponential smoothing of a {t, v} series (t in ms): a run's
 * pull on the trend decays with the time since the previous run, so a burst
 * of same-day runs does not drag the line the way a month of them would.
 * The LAST point is pinned to its real value: smoothing lags, and the line's
 * end is the project's current score, which must not read lower or higher
 * than it is.
 */
export function smoothSeries(points, tauMs) {
  let s = null;
  let prev = null;
  const out = points.map((p) => {
    s = s === null ? p.v : s + (1 - Math.exp(-(p.t - prev) / tauMs)) * (p.v - s);
    prev = p.t;
    return { t: p.t, v: s };
  });
  if (out.length) out[out.length - 1] = { t: points[points.length - 1].t, v: points[points.length - 1].v };
  return out;
}

/** The value in force at time `t` for a step series (held until the next point), or null before the first. */
export function stepValueAt(points, t) {
  let v = null;
  for (const p of points) {
    if (p.t > t) break;
    v = p.v;
  }
  return v;
}
