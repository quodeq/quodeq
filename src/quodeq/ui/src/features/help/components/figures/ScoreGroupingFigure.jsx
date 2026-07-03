// Miniature of the Overview score-history header with its Day/Week/Month
// grouping select, plus a hint of the bucketed bars underneath.
export default function ScoreGroupingFigure() {
  const bars = [42, 55, 48, 62, 58, 70, 66, 74, 71, 80, 77, 84];
  return (
    <div className="sg-figure">
      <div className="sg-figure__header">
        <span className="sg-figure__label">score_history · 12d</span>
        <span className="sg-figure__select">Day &#9662;</span>
      </div>
      <svg viewBox="0 0 320 56" preserveAspectRatio="none">
        {bars.map((h, i) => (
          <rect
            key={i}
            x={4 + i * 26.5}
            y={56 - h * 0.6}
            width="18"
            height={h * 0.6}
            rx="2"
            fill="var(--color-accent)"
            opacity={i === bars.length - 1 ? 1 : 0.45}
          />
        ))}
      </svg>
    </div>
  );
}
