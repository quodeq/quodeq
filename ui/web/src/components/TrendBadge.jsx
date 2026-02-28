import TrendArrow from './TrendArrow';

export default function TrendBadge({ delta, trend, showLabel = false }) {
  if (delta === null || delta === undefined) return null;

  const d = parseFloat(delta);
  const dir = trend || (d > 0 ? 'up' : d < 0 ? 'down' : 'same');
  const label = d > 0.3 ? 'Improving' : d < -0.3 ? 'Declining' : 'Stable';

  return (
    <span className={`trend-badge trend-badge-${dir}`}>
      <span className="trend-badge-delta">
        {d > 0 ? '+' : ''}
        {typeof delta === 'string' ? delta : d.toFixed(1)}
      </span>
      <TrendArrow trend={dir} />
      {showLabel && <span className="trend-badge-label">{label}</span>}
    </span>
  );
}
