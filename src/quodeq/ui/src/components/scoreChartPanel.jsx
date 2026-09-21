/**
 * The chrome around a score-history chart: the panel frame, the stats behind
 * its header line, the tooltip cards the chart shows on hover, and the
 * pairing of a chart with its keyboard-only equivalent.
 *
 * Overview, History and the Explorer's dimension panel all assemble their
 * score chart from these, so a change to the panel shape lands once.
 */
import { SectionLabel, PeriodSelect } from './terminal/index.js';
import ChartKeyboardControls from './ChartKeyboardControls.jsx';
import { ScoreHistoryChart } from './scoreChartParts.jsx';
import { gradeLetter } from '../utils/formatters.js';
import { t } from '../strings/index.js';

/**
 * One tooltip card: the point's date on top, its score and grade below, plus
 * anything else the panel wants to add underneath.
 */
export function ScoreTooltipCard({ label, score, grade, children }) {
  return (
    <div className="run-history-tooltip">
      <span className="rht-date">{label}</span>
      <span className="rht-score">{score} - {grade}</span>
      {children}
    </div>
  );
}

/**
 * The point's score to one decimal, or `fallback` when it never scored.
 *
 * @param {number} value
 * @param {string} fallback
 * @returns {string}
 */
export function tooltipScore(value, fallback) {
  return Number.isFinite(value) ? value.toFixed(1) : fallback;
}

/**
 * The point's date line: the period label once the chart is bucketed by week
 * or month, the run's own date otherwise.
 *
 * @param {{periodLabel?: string, dateLabel?: string}} entry
 * @returns {string}
 */
export function periodOrDateLabel(entry) {
  return entry.periodLabel || entry.dateLabel;
}

/**
 * Build a recharts tooltip component for a score chart.
 *
 * @param {Object} options
 * @param {(entry: Object) => string} options.label Picks the date line off the hovered point.
 * @param {string} options.missingScore Shown in place of a score the point never got.
 * @param {(entry: Object) => React.ReactNode} [options.extra] An extra line under the score.
 * @returns {Function} A component recharts can render as `<Tooltip content>`.
 */
export function makeScoreTooltip({ label, missingScore, extra }) {
  return function ScoreTooltip({ active, payload }) {
    if (!active || !payload?.length) return null;
    const entry = payload[0]?.payload;
    if (!entry) return null;
    return (
      <ScoreTooltipCard
        label={label(entry)}
        score={tooltipScore(entry.numericAverage, missingScore)}
        grade={gradeLetter(entry.overallGrade)}
      >
        {extra ? extra(entry) : null}
      </ScoreTooltipCard>
    );
  };
}

/**
 * Min, max and mean of the finite scores in `data`, or null when none of the
 * points carries a score.
 *
 * @param {Array<{numericAverage: number}>} data
 * @returns {{min: number, max: number, avg: number}|null}
 */
export function computeScoreStats(data) {
  const scores = data.map((d) => d.numericAverage).filter(Number.isFinite);
  if (scores.length === 0) return null;
  return {
    min: Math.min(...scores),
    max: Math.max(...scores),
    avg: scores.reduce((s, n) => s + n, 0) / scores.length,
  };
}

/**
 * The panel a score-history chart sits in: the section, the "SCORE HISTORY ·
 * N<suffix>" label, the period selector when the panel can change granularity
 * and the min/max/avg line when there are scores to summarise.
 */
export function ScoreHistoryPanelFrame({
  ariaLabel, count, suffix, granularity, onGranularityChange, stats, children,
}) {
  return (
    <section className="run-history-panel run-history-panel--terminal panel" aria-label={ariaLabel}>
      <div className="run-history-panel__header">
        <SectionLabel>{t('overview.scoreHistoryLabel')} · {count}{suffix}</SectionLabel>
        <span className="run-history-panel__controls">
          {onGranularityChange && <PeriodSelect value={granularity} onChange={onGranularityChange} />}
          {stats && (
            <span className="run-history-panel__stats">
              {t('overview.minMaxAvg', { min: stats.min.toFixed(1), max: stats.max.toFixed(1), avg: stats.avg.toFixed(1) })}
            </span>
          )}
        </span>
      </div>
      {children}
    </section>
  );
}

/**
 * A score chart with its keyboard-only equivalent beside it: every panel
 * renders the pair, so the wrapper and the controls live together here.
 *
 * @param {Object} props
 * @param {Array} props.data Chart points.
 * @param {Object} props.chart Presentation props for ScoreHistoryChart (height, bars, tooltip).
 * @param {Object} props.interaction Hover/selection props for ScoreHistoryChart.
 * @param {string} props.kbdLabel Group label for the keyboard controls.
 * @param {Array} props.kbdItems One entry per activatable point.
 */
export function ScoreChartWithKeyboard({ data, chart, interaction, kbdLabel, kbdItems }) {
  return (
    <div className="chart-with-kbd">
      <ScoreHistoryChart data={data} {...chart} {...interaction} />
      <ChartKeyboardControls label={kbdLabel} items={kbdItems} />
    </div>
  );
}
