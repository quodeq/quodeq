import { useState, useMemo, useEffect } from 'react';
import { gradeLetter } from '../../../utils/formatters.js';
import ChartKeyboardControls from '../../../components/ChartKeyboardControls.jsx';
import { t } from '../../../strings/index.js';
import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
} from 'recharts';
import {
  cssVar,
  scoreBarColor,
  refLineValues,
  CHART_MARGIN,
  SELECTED_BAR_OPACITY,
  DESELECTED_BAR_OPACITY,
  HISTORY_CHART_HEIGHT,
} from '../../../components/scoreChartHelpers.js';

const MAX_CHART_RUNS = 40;
const CHART_HEIGHT = HISTORY_CHART_HEIGHT;
const HOVER_STROKE_WIDTH = 1.5;
const TREND_LINE_STROKE_WIDTH = 2;
const TREND_LINE_OPACITY = 0.9;

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
  const score = Number.isFinite(entry.numericAverage) ? entry.numericAverage.toFixed(1) : '?';
  const grade = gradeLetter(entry.overallGrade);
  return (
    <div className="run-history-tooltip">
      <span className="rht-date">{entry.dateLabel}</span>
      <span className="rht-score">{score} - {grade}</span>
    </div>
  );
}

function ScoreHistoryChart({ data, interaction }) {
  const { hoveredIndex, setHoveredIndex, selectedRunId, onBarClick } = interaction;
  // Click and hover live on the chart container, not on the Bar. The
  // shared `.run-history-panel .recharts-surface *` rule sets
  // pointer-events:none so the Area/Line layers cannot swallow clicks
  // before they reach the visible bar; in turn we read activeTooltipIndex
  // from Recharts' chart-level events.
  const handleMove = (state) => {
    setHoveredIndex(state?.activeTooltipIndex ?? null);
  };
  const handleClick = (state) => {
    const idx = state?.activeTooltipIndex;
    if (idx == null) return;
    const runId = data[idx]?.runId;
    if (runId) onBarClick?.(runId);
  };
  return (
    <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
      <ComposedChart
        data={data}
        margin={CHART_MARGIN}
        onMouseMove={handleMove}
        onMouseLeave={() => setHoveredIndex(null)}
        onClick={onBarClick ? handleClick : undefined}
        style={onBarClick ? { cursor: 'pointer' } : undefined}
      >
        <XAxis dataKey="dateLabel" hide />
        <YAxis domain={[0, 10]} hide />
        <Tooltip cursor={false} isAnimationActive={false} offset={20} content={<RunHistoryTooltip />} />
        {refLineValues([0, 10]).map((y, i) => (
          <ReferenceLine key={y} y={y} stroke={cssVar('--color-chart-axis')} strokeDasharray="4 4" strokeOpacity={i % 2 ? 0.2 : 0.3} />
        ))}
        <Bar
              dataKey="numericAverage"
          radius={[0, 0, 0, 0]}
          maxBarSize={32}
          isAnimationActive={false}
        >
          {data.map((entry, i) => (
            <Cell
              key={entry.runId ?? i}
              fill={scoreBarColor(entry.numericAverage)}
              opacity={entry.runId === selectedRunId ? SELECTED_BAR_OPACITY : DESELECTED_BAR_OPACITY}
              stroke={hoveredIndex === i ? cssVar('--color-chart-stroke') : 'none'}
              strokeWidth={hoveredIndex === i ? HOVER_STROKE_WIDTH : 0}
            />
          ))}
        </Bar>
        <Line
          isAnimationActive={false}
          dataKey="numericAverage"
          type="monotone"
          stroke={cssVar('--color-accent')}
          strokeOpacity={TREND_LINE_OPACITY}
          strokeWidth={TREND_LINE_STROKE_WIDTH}
          dot={false}
          activeDot={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export default function HistoryChartPanel({ trend = [], selectedRunId = null, onBarClick }) {
  const [hoveredIndex, setHoveredIndex] = useState(null);
  const [, setThemeVersion] = useState(0);
  useEffect(() => {
    const obs = new MutationObserver(() => setThemeVersion((v) => v + 1));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => obs.disconnect();
  }, []);

  const data = useMemo(() => buildTrendData(trend, selectedRunId), [trend, selectedRunId]);

  // Stats computed from the full trend (not just the windowed slice), matching
  // the mockup's LATEST / AVG / MIN / MAX header row. Memoized on `trend` so the
  // O(N) scan doesn't re-run on every hover render (hoveredIndex changes fire a
  // re-render on each mouse move).
  const { latest, min, max, avg } = useMemo(() => {
    const scores = trend
      .map((t) => parseFloat(t.runNumericAverage ?? t.numericAverage))
      .filter((n) => !Number.isNaN(n));
    return {
      latest: scores[0],
      min: scores.length ? Math.min(...scores) : null,
      max: scores.length ? Math.max(...scores) : null,
      avg: scores.length ? scores.reduce((s, n) => s + n, 0) / scores.length : null,
    };
  }, [trend]);

  if (!trend || trend.length < 2) return null;

  const fmt = (n) => (n == null ? '—' : n.toFixed(1));

  const kbdItems = onBarClick
    ? data.map((d, i) => ({
        key: d.runId ?? i,
        text: `${t('history.kbdRunItem', { date: d.dateLabel, score: Number.isFinite(d.numericAverage) ? d.numericAverage.toFixed(1) : '?', grade: gradeLetter(d.overallGrade) })}${d.runId === selectedRunId ? ` ${t('history.selectedSuffix')}` : ''}`,
        onActivate: () => d.runId && onBarClick(d.runId),
      }))
    : [];

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
          interaction={{ hoveredIndex, setHoveredIndex, selectedRunId, onBarClick }}
        />
        <ChartKeyboardControls label={t('history.kbdRunsLabel')} items={kbdItems} />
      </div>
    </section>
  );
}
