import { t } from '../../../../strings/index.js';
// Miniature of the Overview score-history header with its Day/Week/Month
// grouping select, plus a hint of the bucketed bars underneath.

// Illustrative sample bar heights (px, arbitrary) recreating the look of the
// real Overview score-history graphic. Not real data.
const SAMPLE_HEIGHT_1 = 42;
const SAMPLE_HEIGHT_2 = 55;
const SAMPLE_HEIGHT_3 = 48;
const SAMPLE_HEIGHT_4 = 62;
const SAMPLE_HEIGHT_5 = 58;
const SAMPLE_HEIGHT_6 = 70;
const SAMPLE_HEIGHT_7 = 66;
const SAMPLE_HEIGHT_8 = 74;
const SAMPLE_HEIGHT_9 = 71;
const SAMPLE_HEIGHT_10 = 80;
const SAMPLE_HEIGHT_11 = 77;
const SAMPLE_HEIGHT_12 = 84;

// SVG geometry for the bar row.
const SVG_WIDTH = 320;
const SVG_HEIGHT = 56;
const BAR_START_X = 4;
const BAR_SPACING = 26.5;
const BAR_HEIGHT_SCALE = 0.6;
const DIMMED_BAR_OPACITY = 0.45;

export default function ScoreGroupingFigure() {
  const bars = [
    SAMPLE_HEIGHT_1, SAMPLE_HEIGHT_2, SAMPLE_HEIGHT_3, SAMPLE_HEIGHT_4,
    SAMPLE_HEIGHT_5, SAMPLE_HEIGHT_6, SAMPLE_HEIGHT_7, SAMPLE_HEIGHT_8,
    SAMPLE_HEIGHT_9, SAMPLE_HEIGHT_10, SAMPLE_HEIGHT_11, SAMPLE_HEIGHT_12,
  ];
  const BAR_COUNT = bars.length;
  return (
    <div className="sg-figure">
      <div className="sg-figure__header">
        <span className="sg-figure__label">{t('overview.scoreHistoryLabel')} · {BAR_COUNT}{t('granularity.dayAbbrev')}</span>
        <span className="sg-figure__select">{t('common.periodDay')} &#9662;</span>
      </div>
      <svg viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`} preserveAspectRatio="none" aria-hidden="true" focusable="false">
        {bars.map((h, i) => (
          <rect
            key={i}
            x={BAR_START_X + i * BAR_SPACING}
            y={SVG_HEIGHT - h * BAR_HEIGHT_SCALE}
            width="18"
            height={h * BAR_HEIGHT_SCALE}
            rx="2"
            fill="var(--color-accent)"
            opacity={i === bars.length - 1 ? 1 : DIMMED_BAR_OPACITY}
          />
        ))}
      </svg>
    </div>
  );
}
