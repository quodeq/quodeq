import TrendArrow from './TrendArrow';
import { trendDirection, IMPROVING_THRESHOLD, DECLINING_THRESHOLD } from '../utils/trendUtils.js';

export default function TrendBadge({ delta, trend, showLabel = false }) {
  if (delta === null || delta === undefined) return null;

  const d = parseFloat(delta);

  let label;
  if (d > IMPROVING_THRESHOLD) label = 'Improving';
  else if (d < DECLINING_THRESHOLD) label = 'Declining';
  else label = 'Stable';

  const dir = trend || trendDirection(d);

  return (
    <span className={`trend-badge trend-badge-${dir}`}>
      <span className="trend-badge-delta">
        {d > 0 ? '+' : ''}
        {typeof delta === 'string' ? delta : d.toFixed(1)}
      </span>
      <TrendArrow trend={dir} delta={d} />
      {showLabel && <span className="trend-badge-label">{label}</span>}
    </span>
  );
}
