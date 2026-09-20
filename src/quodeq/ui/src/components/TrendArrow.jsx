import { angleFromDelta } from '../utils/formatters.js';

const TREND_ANGLES = { up: 38, 'soft-up': 63, same: 90, stable: 90, 'soft-down': 118, down: 142 };
const ANGLE_UP_MAX = 70;
const ANGLE_SOFT_UP_MAX = 88;
const ANGLE_SOFT_DOWN_MIN = 92;
const ANGLE_DOWN_MIN = 110;

export default function TrendArrow({ trend, delta }) {
  const d = delta !== undefined && delta !== null ? parseFloat(delta) : null;

  const angle = (d !== null && !isNaN(d))
    ? angleFromDelta(d)
    : (TREND_ANGLES[trend] ?? TREND_ANGLES.stable);

  const colorClass =
    angle <= ANGLE_UP_MAX      ? 'trend-up'
    : angle <= ANGLE_SOFT_UP_MAX ? 'trend-soft-up'
    : angle >= ANGLE_DOWN_MIN    ? 'trend-down'
    : angle >= ANGLE_SOFT_DOWN_MIN ? 'trend-soft-down'
    : 'trend-same';

  // A defined-but-invalid delta (e.g. a non-numeric string) parses to NaN:
  // fall back to the same neutral copy the "no delta" branch already uses,
  // same as the angle computation above, instead of literally showing "NaN".
  const title = (d !== null && !isNaN(d)) ? `${d > 0 ? '+' : ''}${d.toFixed(2)}` : (trend ?? '');

  return (
    <span
      className={`trend-arrow ${colorClass}`}
      style={{ display: 'inline-block', transform: `rotate(${Math.round(angle)}deg)` }}
      role="img"
      aria-label={title}
      title={title}
    >↑</span>
  );
}
