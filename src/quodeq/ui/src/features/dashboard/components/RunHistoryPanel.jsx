import { useState } from 'react';
import { formatShortDate, angleFromDelta, scoreTierLabel } from '../../../utils/formatters.js';
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

const MAX_CHART_RUNS = 20;
const CHART_HEIGHT = 160;
const REF_LINE_LOW = 2.5;
const REF_LINE_MID = 5;
const REF_LINE_HIGH = 7.5;
const cssVar = (() => {
  const cache = {};
  return (name, fallback) => {
    if (!(name in cache)) {
      cache[name] = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    }
    return cache[name] || fallback;
  };
})();

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

const DELTA_UP = 1;
const DELTA_SOFT_UP = 0.1;
const DELTA_DOWN = -1;
const DELTA_SOFT_DOWN = -0.1;

// Trend direction — mirrors TrendBadge thresholds
function trendDir(delta) {
  if (delta === null || delta === undefined) return null;
  if (delta > DELTA_UP)        return 'up';
  if (delta > DELTA_SOFT_UP)   return 'soft-up';
  if (delta < DELTA_DOWN)      return 'down';
  if (delta < DELTA_SOFT_DOWN) return 'soft-down';
  return 'same';
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


function buildTrendData(trend, selectedRunId, selectedRunScore) {
  return [...trend].slice(0, MAX_CHART_RUNS).reverse().map((row, i, arr) => {
    const isSelected = row.runId === selectedRunId;
    const numericAverage = isSelected && selectedRunScore != null
      ? parseFloat(selectedRunScore)
      : parseFloat(row.numericAverage);
    return {
      ...row,
      numericAverage,
      delta: i > 0 ? numericAverage - parseFloat(arr[i - 1].numericAverage) : null,
    };
  });
}

function TrendBarLabel({ x, y, width, height, index, data }) {
  const entry = data[index];
  const d = entry?.delta;
  const tier = scoreTierLabel(entry?.numericAverage);
  const cx = x + width / 2;
  const hasDelta = d !== null && d !== undefined;
  const dir = hasDelta ? (trendDir(d) ?? 'same') : null;
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
      <span className="rht-grade">{entry.overallGrade}</span>
    </div>
  );
}

function ScoreHistoryChart({ data, hoveredIndex, setHoveredIndex, selectedRunId, onBarClick, renderTrendLabel }) {
  return (
    <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
      <ComposedChart data={data} margin={{ top: 32, right: 8, bottom: 0, left: -16 }}>
        <CartesianGrid vertical={false} stroke={cssVar('--color-chart-grid')} />
        <XAxis
          dataKey="dateLabel"
          tickFormatter={formatShortDate}
          tick={{ fontSize: 11, fill: cssVar('--color-chart-axis') }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          domain={[0, 10]}
          ticks={[0, REF_LINE_LOW, REF_LINE_MID, REF_LINE_HIGH, 10]}
          tick={{ fontSize: 11, fill: cssVar('--color-chart-axis') }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          cursor={false}
          isAnimationActive={false}
          offset={20}
          content={({ active }) => <RunHistoryTooltip active={active} hoveredIndex={hoveredIndex} data={data} />}
        />
        <ReferenceLine y={REF_LINE_LOW}  stroke={cssVar('--color-chart-axis')} strokeDasharray="4 4" strokeOpacity={0.15} />
        <ReferenceLine y={REF_LINE_MID}  stroke={cssVar('--color-chart-axis')} strokeDasharray="4 4" strokeOpacity={0.3} />
        <ReferenceLine y={REF_LINE_HIGH} stroke={cssVar('--color-chart-axis')} strokeDasharray="4 4" strokeOpacity={0.15} />
        <Bar
          dataKey="numericAverage"
          radius={[3, 3, 0, 0]}
          maxBarSize={40}
          label={renderTrendLabel}
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
              opacity={entry.runId === selectedRunId ? 1 : 0.55}
              stroke={hoveredIndex === i ? cssVar('--color-chart-stroke') : 'none'}
              strokeWidth={hoveredIndex === i ? 1.5 : 0}
            />
          ))}
        </Bar>
        <Line
          isAnimationActive={false}
          dataKey="numericAverage"
          type="monotone"
          stroke={cssVar('--color-chart-line')}
          strokeOpacity={0.55}
          strokeWidth={2.5}
          dot={false}
          activeDot={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export default function RunHistoryPanel({ trend = [], selectedRunId = null, selectedRunScore, onBarClick }) {
  const [hoveredIndex, setHoveredIndex] = useState(null);

  if (!trend || trend.length < 2) return null;

  const data = buildTrendData(trend, selectedRunId, selectedRunScore);
  const renderTrendLabel = (props) => <TrendBarLabel {...props} data={data} />;

  return (
    <section className="run-history-panel panel" aria-label="Score history chart">
      <div className="run-history-header">
        <span className="run-history-title">Score History</span>
      </div>
      <ScoreHistoryChart
        data={data} hoveredIndex={hoveredIndex} setHoveredIndex={setHoveredIndex}
        selectedRunId={selectedRunId} onBarClick={onBarClick} renderTrendLabel={renderTrendLabel}
      />
    </section>
  );
}
