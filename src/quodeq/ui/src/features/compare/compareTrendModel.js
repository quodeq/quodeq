/**
 * Pure geometry for CompareDuelTrend: the two-series time/value domain and
 * the monotone cubic curve through a set of points. Nothing here fetches.
 */
import { scoreDomain } from '../../components/scoreChartHelpers.js';

/**
 * Time/value bounds spanning both projects' series. Runs land at their real
 * dates (not evenly spaced), so the time half is a plain min/max; the value
 * half calls scoreDomain (score charts everywhere use the same half-point
 * padding + outward rounding) instead of re-deriving it.
 */
export function trendDomain(series) {
  const times = series.flat().map((e) => new Date(e.dateISO).getTime());
  const values = series.flat().map((e) => e.value);
  const [v0, v1] = scoreDomain(values);
  return {
    t0: Math.min(...times),
    t1: Math.max(...times),
    v0,
    v1,
  };
}

/**
 * Monotone cubic (Fritsch-Carlson) path through the points: soft curves
 * that still pass through every value and never overshoot a peak or put a
 * wobble on a plateau — the same interpolation the Overview's line uses.
 */
export function monotonePath(pts) {
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
