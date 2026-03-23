import TrendArrow from './TrendArrow';

const IMPROVING_THRESHOLD = 1;
const DECLINING_THRESHOLD = -1;
const SOFT_UP_THRESHOLD = 0.1;
const SOFT_DOWN_THRESHOLD = -0.1;

export default function TrendBadge({ delta, trend, showLabel = false }) {
  if (delta === null || delta === undefined) return null;

  const d = parseFloat(delta);

  let label;
  if (d > IMPROVING_THRESHOLD) label = 'Improving';
  else if (d < DECLINING_THRESHOLD) label = 'Declining';
  else label = 'Stable';

  let dir;
  if (trend) dir = trend;
  else if (d > IMPROVING_THRESHOLD) dir = 'up';
  else if (d > SOFT_UP_THRESHOLD) dir = 'soft-up';
  else if (d < DECLINING_THRESHOLD) dir = 'down';
  else if (d < SOFT_DOWN_THRESHOLD) dir = 'soft-down';
  else dir = 'same';

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
