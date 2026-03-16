// Rotation: 0° = straight up (↑), 90° = horizontal (→), 180° = straight down (↓)
// sqrt curve: non-zero deltas always tilt; max arc 55° keeps small changes subtle
function angleFromDelta(d) {
  const clamped = Math.max(-4, Math.min(4, d));
  return 90 - Math.sign(clamped) * Math.sqrt(Math.abs(clamped) / 4) * 55;
}

const TREND_ANGLES = { up: 38, 'soft-up': 63, same: 90, stable: 90, 'soft-down': 118, down: 142 };

export default function TrendArrow({ trend, delta }) {
  const d = delta !== undefined && delta !== null ? parseFloat(delta) : null;

  const angle = (d !== null && !isNaN(d))
    ? angleFromDelta(d)
    : (TREND_ANGLES[trend] ?? 90);

  const colorClass =
    angle <= 70  ? 'trend-up'
    : angle <= 88  ? 'trend-soft-up'
    : angle >= 110 ? 'trend-down'
    : angle >= 92  ? 'trend-soft-down'
    : 'trend-same';

  const title = d !== null ? `${d > 0 ? '+' : ''}${d.toFixed(2)}` : (trend ?? '');

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
