import TrendArrow from './TrendArrow';

export default function TrendBadge({ delta, trend, showLabel = false }) {
  if (delta === null || delta === undefined) return null;

  const d = parseFloat(delta);
  const label = d > 1 ? 'Improving' : d < -1 ? 'Declining' : 'Stable';
  const dir = trend || (d > 1 ? 'up' : d > 0.1 ? 'soft-up' : d < -1 ? 'down' : d < -0.1 ? 'soft-down' : 'same');

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
