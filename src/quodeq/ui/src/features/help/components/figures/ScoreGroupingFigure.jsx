import { t } from '../../../../strings/index.js';
// Miniature of the Overview score-history header with its Day/Week/Month
// grouping select, plus a hint of the bucketed bars underneath.
export default function ScoreGroupingFigure() {
  const bars = [42, 55, 48, 62, 58, 70, 66, 74, 71, 80, 77, 84];
  const BAR_COUNT = bars.length;
  return (
    <div className="sg-figure">
      <div className="sg-figure__header">
        <span className="sg-figure__label">{t('overview.scoreHistoryLabel')} · {BAR_COUNT}{t('granularity.dayAbbrev')}</span>
        <span className="sg-figure__select">{t('common.periodDay')} &#9662;</span>
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
