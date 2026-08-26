/**
 * CompareTrendLine — tiny line sparkline for a row's score trend, a
 * miniature of the Overview's score-history line rather than a bar
 * histogram. Points are evenly spaced oldest -> newest; the stroke takes
 * the grade colour of the LATEST score and a dot marks it.
 */
import { scoreGradeColorVar } from '../../../utils/formatters.js';

const HEIGHT = 20;
const PAD = 2;

export default function CompareTrendLine({ scores, width = 90 }) {
  if (!scores || scores.length < 2) return null;
  // Absolute 0-10 scale, matching the score-history charts: the spark's
  // height position means score, not a magnified window. The duel trend
  // is the one deliberately zoomed view.
  const point = (s, i) => {
    const x = PAD + (i / (scores.length - 1)) * (width - PAD * 2);
    const y = HEIGHT - PAD - (s / 10) * (HEIGHT - PAD * 2);
    return [x, y];
  };
  const pts = scores.map((s, i) => point(s, i).map((v) => v.toFixed(1)).join(',')).join(' ');
  const [lastX, lastY] = point(scores[scores.length - 1], scores.length - 1);
  const color = scoreGradeColorVar(scores[scores.length - 1]);
  return (
    <svg className="compare-trendline" width={width} height={HEIGHT} aria-hidden="true">
      <polyline points={pts} style={{ stroke: color }} />
      <circle cx={lastX.toFixed(1)} cy={lastY.toFixed(1)} r="2" style={{ fill: color }} />
    </svg>
  );
}
