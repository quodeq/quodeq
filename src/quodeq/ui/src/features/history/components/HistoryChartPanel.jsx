import { useState, useMemo } from 'react';
import { formatShortDate, angleFromDelta, scoreTierLabel, gradeLetter } from '../../../utils/formatters.js';
import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
} from 'recharts';
import { trendDirection } from '../../../utils/trendUtils.js';

const MAX_CHART_RUNS = 40;
const CHART_HEIGHT = 160;
const REF_LINE_LOW = 2.5;
const REF_LINE_MID = 5;
const REF_LINE_HIGH = 7.5;
const DESELECTED_BAR_OPACITY = 0.55;
const HOVER_STROKE_WIDTH = 1.5;
const TREND_LINE_STROKE_WIDTH = 2.5;
const TREND_LINE_OPACITY = 0.55;
const _cssVarCache = {};
const cssVar = (name, fallback) => {
  if (name in _cssVarCache) return _cssVarCache[name] || fallback;
  const val = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  _cssVarCache[name] = val;
  return val || fallback;
};

const SCORE_EXEMPLARY = 9;
const SCORE_GOOD = 7;
const SCORE_ADEQUATE = 5;
const SCORE_POOR = 3;

function scoreBarColor(score) {
  const n = parseFloat(score);
  if (isNaN(n)) return cssVar('--color-accent');
  if (n >= SCORE_EXEMPLARY) return cssVar('--color-grade-top-text');
  if (n >= SCORE_GOOD)      return cssVar('--color-grade-high-text');
  if (n >= SCORE_ADEQUATE)  return cssVar('--color-grade-mid-text');
  if (n >= SCORE_POOR)      return cssVar('--color-grade-low-text');
  return cssVar('--color-grade-bottom-text');
}

function trendColor(dir) {
  const map = {
    'up':         '--color-trend-up',
    'soft-up':    '--color-trend-soft-up',
    'same':       '--color-text-muted',
    'soft-down':  '--color-trend-soft-down',
    'down':       '--color-trend-down',
  };
  return cssVar(map[dir] ?? '--color-text-muted');
}


function windowAroundSelected(trend, selectedRunId) {
  if (trend.length <= MAX_CHART_RUNS) return trend;
  const idx = trend.findIndex((r) => r.runId === selectedRunId);
  if (idx < 0) return trend.slice(0, MAX_CHART_RUNS);
  // Center the window on the selected run
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
  return [...windowed].reverse().map((row, i, arr) => {
    const runScore = parseFloat(row.runNumericAverage ?? row.numericAverage);
    return {
      ...row,
      numericAverage: runScore,
      delta: i > 0 ? runScore - parseFloat(arr[i - 1].numericAverage) : null,
    };
  });
}

function TrendBarLabel({ x, y, width, height, index, data }) {
  const entry = data[index];
  const d = entry?.delta;
  const tier = scoreTierLabel(entry?.numericAverage);
  const cx = x + width / 2;
  const hasDelta = d !== null && d !== undefined;
  const dir = hasDelta ? (trendDirection(d) ?? 'same') : null;
  const color = hasDelta ? trendColor(dir) : null;
  return (
    <g>
      {hasDelta && (
        <>
          <text x={cx} y={y - 25} textAnchor="middle" fontSize={9} fill={color}>
            {d > 0 ? `+${d.toFixed(1)}` : d.toFixed(1)}
          </text>
          <text
            x={cx} y={y - 14}
            textAnchor="middle" dominantBaseline="central"
            fontSize={11} fill={color}
            transform={`rotate(${Math.round(angleFromDelta(d))}, ${cx}, ${y - 14})`}
          >↑</text>
        </>
      )}
      {tier && height > 12 && (
        <text
          x={cx} y={y + Math.min(height / 2, 9)}
          textAnchor="middle" dominantBaseline="central"
          fontSize={9} fill="white" fillOpacity={0.85}
        >{tier}</text>
      )}
    </g>
  );
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

function buildAxisTick() {
  return { fontSize: 11, fill: cssVar('--color-chart-axis') };
}

function ReferenceLines() {
  const stroke = cssVar('--color-chart-axis');
  return (
    <>
      <ReferenceLine y={REF_LINE_LOW}  stroke={stroke} strokeDasharray="4 4" strokeOpacity={0.15} />
      <ReferenceLine y={REF_LINE_MID}  stroke={stroke} strokeDasharray="4 4" strokeOpacity={0.3} />
      <ReferenceLine y={REF_LINE_HIGH} stroke={stroke} strokeDasharray="4 4" strokeOpacity={0.15} />
    </>
  );
}

function ScoreHistoryChart({ data, interaction, renderTrendLabel }) {
  const { hoveredIndex, setHoveredIndex, selectedRunId, onBarClick } = interaction;
  const axisTick = buildAxisTick();
  return (
    <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
      <ComposedChart data={data} margin={{ top: 32, right: 8, bottom: 0, left: -16 }}>
        <CartesianGrid vertical={false} stroke={cssVar('--color-chart-grid')} />
        <XAxis dataKey="dateLabel" tickFormatter={formatShortDate} tick={axisTick} axisLine={false} tickLine={false} />
        <YAxis domain={[0, 10]} ticks={[0, REF_LINE_LOW, REF_LINE_MID, REF_LINE_HIGH, 10]} tick={axisTick} axisLine={false} tickLine={false} />
        <Tooltip cursor={false} isAnimationActive={false} offset={20} content={({ active }) => <RunHistoryTooltip active={active} hoveredIndex={hoveredIndex} data={data} />} />
        <ReferenceLines />
        <Bar dataKey="numericAverage" radius={[3, 3, 0, 0]} maxBarSize={40} label={renderTrendLabel} isAnimationActive={false} cursor={onBarClick ? 'pointer' : 'default'} onMouseEnter={(_, index) => setHoveredIndex(index)} onMouseLeave={() => setHoveredIndex(null)} onClick={(entry) => onBarClick?.(entry.runId)}>
          {data.map((entry, i) => (
            <Cell key={entry.runId ?? i} fill={scoreBarColor(entry.numericAverage)} opacity={entry.runId === selectedRunId ? 1 : DESELECTED_BAR_OPACITY} stroke={hoveredIndex === i ? cssVar('--color-chart-stroke') : 'none'} strokeWidth={hoveredIndex === i ? HOVER_STROKE_WIDTH : 0} />
          ))}
        </Bar>
        <Line isAnimationActive={false} dataKey="numericAverage" type="monotone" stroke={cssVar('--color-chart-line')} strokeOpacity={TREND_LINE_OPACITY} strokeWidth={TREND_LINE_STROKE_WIDTH} dot={false} activeDot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export default function RunHistoryPanel({ trend = [], selectedRunId = null, onBarClick }) {
  const [hoveredIndex, setHoveredIndex] = useState(null);

  if (!trend || trend.length < 2) return null;

  const data = useMemo(() => buildTrendData(trend, selectedRunId), [trend, selectedRunId]);
  const renderTrendLabel = (props) => <TrendBarLabel {...props} data={data} />;

  return (
    <section className="run-history-panel panel" aria-label="Score history chart">
      <div className="run-history-header">
        <span className="run-history-title">Score History</span>
      </div>
      <ScoreHistoryChart
        data={data}
        interaction={{ hoveredIndex, setHoveredIndex, selectedRunId, onBarClick }}
        renderTrendLabel={renderTrendLabel}
      />
    </section>
  );
}
