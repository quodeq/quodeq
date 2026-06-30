import { useState, useMemo, useEffect } from 'react';
import { gradeLetter } from '../../../utils/formatters.js';
import ChartKeyboardControls from '../../../components/ChartKeyboardControls.jsx';
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
  REF_LINE_LOW,
  REF_LINE_MID,
  REF_LINE_HIGH,
  CHART_MARGIN,
  SELECTED_BAR_OPACITY,
  DESELECTED_BAR_OPACITY,
} from '../../../components/scoreChartHelpers.js';

const MAX_CHART_RUNS = 40;
const CHART_HEIGHT = 220;
const REF_LINE_FLOOR = 0;
const REF_LINE_CEIL = 10;
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
        <ReferenceLine y={REF_LINE_FLOOR} stroke={cssVar('--color-chart-axis')} strokeDasharray="4 4" strokeOpacity={0.6} />
        <ReferenceLine y={REF_LINE_LOW}   stroke={cssVar('--color-chart-axis')} strokeDasharray="4 4" strokeOpacity={0.45} />
        <ReferenceLine y={REF_LINE_MID}   stroke={cssVar('--color-chart-axis')} strokeDasharray="4 4" strokeOpacity={0.45} />
        <ReferenceLine y={REF_LINE_HIGH}  stroke={cssVar('--color-chart-axis')} strokeDasharray="4 4" strokeOpacity={0.45} />
        <ReferenceLine y={REF_LINE_CEIL}  stroke={cssVar('--color-chart-axis')} strokeDasharray="4 4" strokeOpacity={0.6} />
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

  if (!trend || trend.length < 2) return null;

  // Stats computed from the full trend (not just the windowed slice), matching
  // the mockup's LATEST / AVG / MIN / MAX header row.
  const scores = trend
    .map((t) => parseFloat(t.runNumericAverage ?? t.numericAverage))
    .filter((n) => !Number.isNaN(n));
  const latest = scores[0];
  const min = scores.length ? Math.min(...scores) : null;
  const max = scores.length ? Math.max(...scores) : null;
  const avg = scores.length ? scores.reduce((s, n) => s + n, 0) / scores.length : null;

  const fmt = (n) => (n == null ? '—' : n.toFixed(1));

  const kbdItems = onBarClick
    ? data.map((d, i) => ({
        key: d.runId ?? i,
        text: `${d.dateLabel}: ${Number.isFinite(d.numericAverage) ? d.numericAverage.toFixed(1) : '?'}, grade ${gradeLetter(d.overallGrade)}${d.runId === selectedRunId ? ' (selected)' : ''}`,
        onActivate: () => d.runId && onBarClick(d.runId),
      }))
    : [];

  return (
    <section className="run-history-panel run-history-panel--terminal panel" aria-label="Score history chart">
      <div className="run-history-panel__header">
        <span className="term-section-label__text">SCORE_HISTORY</span>
        <span className="run-history-panel__stats">
          LATEST {fmt(latest)} · AVG {fmt(avg)} · MIN {fmt(min)} · MAX {fmt(max)}
        </span>
      </div>
      <div className="chart-with-kbd">
        <ScoreHistoryChart
          data={data}
          interaction={{ hoveredIndex, setHoveredIndex, selectedRunId, onBarClick }}
        />
        <ChartKeyboardControls label="Score history runs — Tab to a run, Enter to open it" items={kbdItems} />
      </div>
    </section>
  );
}
