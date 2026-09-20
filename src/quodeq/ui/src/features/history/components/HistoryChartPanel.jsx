import { useState, useMemo, useEffect } from 'react';
import { gradeLetter } from '../../../utils/formatters.js';
import ChartKeyboardControls from '../../../components/ChartKeyboardControls.jsx';
import { t } from '../../../strings/index.js';
import {
  ScoreHistoryChart,
  ScoreTooltipCard,
  tooltipScore,
} from '../../../components/scoreChartParts.jsx';
import { HISTORY_CHART_HEIGHT } from '../../../components/scoreChartHelpers.js';
import { computeHistoryChartStats, buildHistoryKbdItems } from './historyChartStats.js';
import { DATA_THEME_ATTR } from '../../../constants.js';

const MAX_CHART_RUNS = 40;
const CHART_HEIGHT = HISTORY_CHART_HEIGHT;
const MAX_BAR_SIZE = 32;
const MISSING_SCORE = '?';

function windowAroundSelected(trend, selectedRunId) {
  if (trend.length <= MAX_CHART_RUNS) return trend;
  const idx = trend.findIndex((r) => r.runId === selectedRunId);
  if (idx < 0) return trend.slice(0, MAX_CHART_RUNS);
  const half = Math.floor(MAX_CHART_RUNS / 2);
  let start = Math.max(0, idx - half);
  let end = start + MAX_CHART_RUNS;
  if (end > trend.length) {
    end = trend.length;
    start = Math.max(0, end - MAX_CHART_RUNS);
  }
  return trend.slice(start, end);
}

function buildTrendData(trend, selectedRunId) {
  const windowed = windowAroundSelected(trend, selectedRunId);
  return [...windowed].reverse().map((row) => {
    const runScore = parseFloat(row.runNumericAverage ?? row.numericAverage);
    return { ...row, numericAverage: runScore };
  });
}

function RunHistoryTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const entry = payload[0]?.payload;
  if (!entry) return null;
  return (
    <ScoreTooltipCard
      label={entry.dateLabel}
      score={tooltipScore(entry.numericAverage, MISSING_SCORE)}
      grade={gradeLetter(entry.overallGrade)}
    />
  );
}

export default function HistoryChartPanel({ trend = [], selectedRunId = null, onBarClick }) {
  const [hoveredIndex, setHoveredIndex] = useState(null);
  const [, setThemeVersion] = useState(0);
  useEffect(() => {
    const obs = new MutationObserver(() => setThemeVersion((v) => v + 1));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: [DATA_THEME_ATTR] });
    return () => obs.disconnect();
  }, []);

  const data = useMemo(() => buildTrendData(trend, selectedRunId), [trend, selectedRunId]);

  // Stats computed from the full trend (not just the windowed slice), matching
  // the mockup's LATEST / AVG / MIN / MAX header row. Memoized on `trend` so the
  // O(N) scan doesn't re-run on every hover render (hoveredIndex changes fire a
  // re-render on each mouse move).
  const { latest, min, max, avg } = useMemo(() => computeHistoryChartStats(trend), [trend]);

  if (!trend || trend.length < 2) return null;

  const fmt = (n) => (n == null ? '—' : n.toFixed(1));

  const kbdItems = buildHistoryKbdItems({ data, onBarClick, selectedRunId });

  return (
    <section className="run-history-panel run-history-panel--terminal panel" aria-label={t('overview.scoreHistoryAria')}>
      <div className="run-history-panel__header">
        <span className="term-section-label__text">{t('history.scoreHistoryHeader')}</span>
        <span className="run-history-panel__stats">
          {t('history.latestAvgMinMax', { latest: fmt(latest), avg: fmt(avg), min: fmt(min), max: fmt(max) })}
        </span>
      </div>
      <div className="chart-with-kbd">
        <ScoreHistoryChart
          data={data}
          height={CHART_HEIGHT}
          maxBarSize={MAX_BAR_SIZE}
          tooltip={<RunHistoryTooltip />}
          hoveredIndex={hoveredIndex}
          setHoveredIndex={setHoveredIndex}
          selectedRunId={selectedRunId}
          onActivate={onBarClick ? (point) => onBarClick(point.runId) : undefined}
        />
        <ChartKeyboardControls label={t('history.kbdRunsLabel')} items={kbdItems} />
      </div>
    </section>
  );
}
