import TrendArrow from './TrendArrow';
import { trendDirection, IMPROVING_THRESHOLD, DECLINING_THRESHOLD } from '../utils/trendUtils.js';

/**
 * @param {{delta: number|string|null, trend?: string, arrow?: string, showLabel?: boolean, invert?: boolean}} props
 *   `invert` is for counts where lower is better (majors): the text keeps
 *   the real sign, while the colour follows the negated delta. `arrow`
 *   points the arrow on its own (a count's arrow follows the number, not
 *   the colour); without it the arrow points the way the colour does.
 */
export default function TrendBadge({ delta, trend, arrow, showLabel = false, invert = false }) {
  if (delta === null || delta === undefined) return null;

  const d = parseFloat(delta);
  const signal = invert ? -d : d;

  let label;
  if (signal > IMPROVING_THRESHOLD) label = 'Improving';
  else if (signal < DECLINING_THRESHOLD) label = 'Declining';
  else label = 'Stable';

  const dir = trend || trendDirection(signal);

  return (
    <span className={`trend-badge trend-badge-${dir}`}>
      <span className="trend-badge-delta">
        {d > 0 ? '+' : ''}
        {typeof delta === 'string' ? delta : d.toFixed(1)}
      </span>
      <TrendArrow trend={arrow || dir} delta={invert ? null : d} />
      {showLabel && <span className="trend-badge-label">{label}</span>}
    </span>
  );
}
