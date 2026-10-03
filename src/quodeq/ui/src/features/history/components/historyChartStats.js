import { gradeLetter } from '../../../utils/formatters.js';
import { t } from '../../../strings/index.js';
import { runCounts } from '../../dashboard/headlineStats.js';

/**
 * Stats computed from the full trend (not just the windowed slice), matching
 * the mockup's LATEST / AVG / MIN / MAX header row. The panel calls this
 * from inside a useMemo(fn, [trend]) so the O(N) scan doesn't re-run on
 * every hover render (hoveredIndex changes fire a re-render on each mouse
 * move).
 */
export function computeHistoryChartStats(trend) {
  const scores = trend
    .map((point) => parseFloat(point.runNumericAverage ?? point.numericAverage))
    .filter((n) => !Number.isNaN(n));
  return {
    latest: scores[0],
    min: scores.length ? Math.min(...scores) : null,
    max: scores.length ? Math.max(...scores) : null,
    avg: scores.length ? scores.reduce((s, n) => s + n, 0) / scores.length : null,
  };
}

/**
 * Keyboard-accessible items mirroring the chart's bars, one per plotted run.
 */
export function buildHistoryKbdItems({ data, onBarClick, selectedRunId }) {
  return onBarClick
    ? data.map((d, i) => ({
        key: d.runId ?? i,
        text: `${t('history.kbdRunItem', { date: d.dateLabel, score: Number.isFinite(d.numericAverage) ? d.numericAverage.toFixed(1) : '?', grade: gradeLetter(d.overallGrade) })}${d.runId === selectedRunId ? ` ${t('history.selectedSuffix')}` : ''}`,
        onActivate: () => d.runId && onBarClick(d.runId),
      }))
    : [];
}

function windowAroundSelected(trend, selectedRunId, windowSize) {
  if (trend.length <= windowSize) return trend;
  const idx = trend.findIndex((r) => r.runId === selectedRunId);
  if (idx < 0) return trend.slice(0, windowSize);
  const half = Math.floor(windowSize / 2);
  let start = Math.max(0, idx - half);
  let end = start + windowSize;
  if (end > trend.length) {
    end = trend.length;
    start = Math.max(0, end - windowSize);
  }
  return trend.slice(start, end);
}

/**
 * The History chart's points: a window of up to `windowSize` runs around the
 * selected one, oldest first, each with the run's own score and its
 * criticals, majors and open types (over the dimensions on show).
 */
export function buildHistoryChartRows(trend, selectedRunId, windowSize) {
  const windowed = windowAroundSelected(trend, selectedRunId, windowSize);
  return [...windowed].reverse().map((row) => ({
    ...row,
    numericAverage: parseFloat(row.runNumericAverage ?? row.numericAverage),
    ...runCounts(row),
  }));
}
