import { useState, useMemo, useEffect } from 'react';
import { gradeLetter } from '../../../utils/formatters.js';
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

const MAX_CHART_RUNS = 40;
const CHART_HEIGHT = 220;
const REF_LINE_LOW = 2.5;
const REF_LINE_MID = 5;
const REF_LINE_HIGH = 7.5;
const REF_LINE_FLOOR = 0;
const REF_LINE_CEIL = 10;
const DESELECTED_BAR_OPACITY = 0.62;
const CHART_MARGIN = { top: 8, right: 0, bottom: 0, left: 0 };
const HOVER_STROKE_WIDTH = 1.5;
const TREND_LINE_STROKE_WIDTH = 2;
const TREND_LINE_OPACITY = 0.9;

const _cssVarCache = new Map();
const cssVar = (name, fallback) => {
  if (_cssVarCache.has(name)) return _cssVarCache.get(name) || fallback;
  if (typeof document === 'undefined') return fallback;
  const val = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  _cssVarCache.set(name, val);
  return val || fallback;
};
if (typeof document !== 'undefined') {
  new MutationObserver(() => _cssVarCache.clear()).observe(
    document.documentElement, { attributes: true, attributeFilter: ['class', 'data-theme'] },
  );
}

const GRADE_CSS_VARS = {
  'grade-top':    '--color-grade-top-text',
  'grade-high':   '--color-grade-high-text',
  'grade-mid':    '--color-grade-mid-text',
  'grade-low':    '--color-grade-low-text',
  'grade-bottom': '--color-grade-bottom-text',
};

function scoreBarColor(score) {
  const n = parseFloat(score);
  if (Number.isNaN(n)) return cssVar('--color-accent');
  if (n >= 9) return cssVar(GRADE_CSS_VARS['grade-top']);
  if (n >= 7) return cssVar(GRADE_CSS_VARS['grade-high']);
  if (n >= 5) return cssVar(GRADE_CSS_VARS['grade-mid']);
  if (n >= 3) return cssVar(GRADE_CSS_VARS['grade-low']);
  return cssVar(GRADE_CSS_VARS['grade-bottom']);
}

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

function RunHistoryTooltip({ active, hoveredIndex, data }) {
  if (!active || hoveredIndex === null) return null;
  const entry = data[hoveredIndex];
  if (!entry) return null;
  return (
    <div className="run-history-tooltip">
      <span className="rht-date">{entry.dateLabel}</span>
      <span className="rht-score">{entry.numericAverage.toFixed(1)} / 10</span>
      <span className="rht-grade">{gradeLetter(entry.overallGrade)}</span>
    </div>
  );
}

function ScoreHistoryChart({ data, interaction }) {
  const { hoveredIndex, setHoveredIndex, selectedRunId, onBarClick } = interaction;
  return (
    <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
      <ComposedChart data={data} margin={CHART_MARGIN}>
        <XAxis dataKey="dateLabel" hide />
        <YAxis domain={[0, 10]} hide />
        <Tooltip cursor={false} isAnimationActive={false} offset={20} content={({ active }) => <RunHistoryTooltip active={active} hoveredIndex={hoveredIndex} data={data} />} />
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
          cursor={onBarClick ? 'pointer' : 'default'}
          onMouseEnter={(_, index) => setHoveredIndex(index)}
          onMouseLeave={() => setHoveredIndex(null)}
          onClick={(entry) => onBarClick?.(entry.runId)}
        >
          {data.map((entry, i) => (
            <Cell
              key={entry.runId ?? i}
              fill={scoreBarColor(entry.numericAverage)}
              opacity={entry.runId === selectedRunId ? 1 : DESELECTED_BAR_OPACITY}
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

  return (
    <section className="run-history-panel run-history-panel--terminal panel" aria-label="Score history chart">
      <div className="run-history-panel__header">
        <span className="term-section-label__text">SCORE_HISTORY</span>
        <span className="run-history-panel__stats">
          LATEST {fmt(latest)} · AVG {fmt(avg)} · MIN {fmt(min)} · MAX {fmt(max)}
        </span>
      </div>
      <ScoreHistoryChart
        data={data}
        interaction={{ hoveredIndex, setHoveredIndex, selectedRunId, onBarClick }}
      />
    </section>
  );
}
