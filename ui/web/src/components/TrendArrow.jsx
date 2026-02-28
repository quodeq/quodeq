export default function TrendArrow({ trend }) {
  if (trend === 'up') return <span className="trend-arrow trend-up" title="Improved">↑</span>;
  if (trend === 'down') return <span className="trend-arrow trend-down" title="Declined">↓</span>;
  if (trend === 'stable' || trend === 'same') return <span className="trend-arrow trend-same" title="No change">→</span>;
  return null;
}
