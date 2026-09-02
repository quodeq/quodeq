import { gradeLetter } from '../../../utils/formatters.js';
import { t } from '../../../strings/index.js';

/**
 * Stats computed from the full trend (not just the windowed slice), matching
 * the mockup's LATEST / AVG / MIN / MAX header row. Extracted verbatim from
 * HistoryChartPanel.jsx; still called from inside a useMemo(fn, [trend])
 * there so the O(N) scan doesn't re-run on every hover render (hoveredIndex
 * changes fire a re-render on each mouse move).
 */
export function computeHistoryChartStats(trend) {
  const scores = trend
    .map((t) => parseFloat(t.runNumericAverage ?? t.numericAverage))
    .filter((n) => !Number.isNaN(n));
  return {
    latest: scores[0],
    min: scores.length ? Math.min(...scores) : null,
    max: scores.length ? Math.max(...scores) : null,
    avg: scores.length ? scores.reduce((s, n) => s + n, 0) / scores.length : null,
  };
}

/**
 * Keyboard-accessible items mirroring the chart's bars. Extracted verbatim
 * from HistoryChartPanel.jsx.
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
