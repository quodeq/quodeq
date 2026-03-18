import TrendArrow from './TrendArrow';

const IMPROVING_THRESHOLD = 1;
const DECLINING_THRESHOLD = -1;
const SOFT_UP_THRESHOLD = 0.1;
const SOFT_DOWN_THRESHOLD = -0.1;

export default function TrendBadge({ delta, trend, showLabel = false }) {
  if (delta === null || delta === undefined) return null;

  const d = parseFloat(delta);
  const label = d > IMPROVING_THRESHOLD ? 'Improving' : d < DECLINING_THRESHOLD ? 'Declining' : 'Stable';
  const dir = trend || (d > IMPROVING_THRESHOLD ? 'up' : d > SOFT_UP_THRESHOLD ? 'soft-up' : d < DECLINING_THRESHOLD ? 'down' : d < SOFT_DOWN_THRESHOLD ? 'soft-down' : 'same');

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
