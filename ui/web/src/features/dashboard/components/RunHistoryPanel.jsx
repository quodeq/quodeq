import { useState } from 'react';
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
function cssVar(name, fallback) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

function scoreBarColor(score) {
  const n = parseFloat(score);
  if (isNaN(n)) return cssVar('--color-accent');
  if (n >= 9) return cssVar('--color-grade-top-text');   // exemplary
  if (n >= 7) return cssVar('--color-grade-high-text');  // good
  if (n >= 5) return cssVar('--color-grade-mid-text');   // adequate
  if (n >= 3) return cssVar('--color-grade-low-text');   // poor
  return cssVar('--color-grade-bottom-text');            // critical
}

// Mirrors angleFromDelta in TrendArrow — sqrt curve, max arc 55°
function angleFromDelta(d) {
  const clamped = Math.max(-4, Math.min(4, d));
  return 90 - Math.sign(clamped) * Math.sqrt(Math.abs(clamped) / 4) * 55;
}

// Trend direction — mirrors TrendBadge thresholds
function trendDir(delta) {
  if (delta === null || delta === undefined) return null;
  if (delta > 1)    return 'up';
  if (delta > 0.1)  return 'soft-up';
  if (delta < -1)   return 'down';
  if (delta < -0.1) return 'soft-down';
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


export default function RunHistoryPanel({ trend = [], selectedRunId = null, selectedRunScore, onBarClick }) {
  const [hoveredIndex, setHoveredIndex] = useState(null);

  // Need at least 2 data points to render a meaningful trend line
  if (!trend || trend.length < 2) return null;

  // Take the 20 most recent runs (trend is newest-first), then display oldest→newest.
  // For the selected run, use the accumulated score so the bar matches the acc-eval-hero.
  const data = [...trend].slice(0, 20).reverse().map((row, i, arr) => {
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

  // Custom label above each bar: rotated ↑ arrow + delta value
  const renderTrendLabel = ({ x, y, width, index }) => {
    const entry = data[index];
    const d = entry?.delta;
    if (d === null || d === undefined) return null;
    const dir = trendDir(d) ?? 'same';
    const color = trendColor(dir);
    const angle = Math.round(angleFromDelta(d));
    const cx = x + width / 2;
    const arrowY = y - 14;
    const deltaStr = d > 0 ? `+${d.toFixed(1)}` : d.toFixed(1);
    return (
      <g>
        <text x={cx} y={y - 25} textAnchor="middle" fontSize={9} fill={color}>
          {deltaStr}
        </text>
        <text
          x={cx} y={arrowY}
          textAnchor="middle" dominantBaseline="central"
          fontSize={11} fill={color}
          transform={`rotate(${angle}, ${cx}, ${arrowY})`}
        >↑</text>
      </g>
    );
  };

  return (
    <section className="run-history-panel panel">
      <div className="run-history-header">
        <span className="run-history-title">Score History</span>
      </div>
      <ResponsiveContainer width="100%" height={160}>
        <ComposedChart data={data} margin={{ top: 32, right: 8, bottom: 0, left: -16 }}>
          <CartesianGrid vertical={false} stroke={cssVar('--color-chart-grid')} />
          <XAxis
            dataKey="dateLabel"
            tick={{ fontSize: 11, fill: cssVar('--color-chart-axis') }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            domain={[0, 10]}
            ticks={[0, 2.5, 5, 7.5, 10]}
            tick={{ fontSize: 11, fill: cssVar('--color-chart-axis') }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            cursor={false}
            isAnimationActive={false}
            offset={20}
            content={({ active }) => {
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
            }}
          />
          <ReferenceLine y={2.5} stroke={cssVar('--color-chart-axis')} strokeDasharray="4 4" strokeOpacity={0.15} />
          <ReferenceLine y={5}   stroke={cssVar('--color-chart-axis')} strokeDasharray="4 4" strokeOpacity={0.3} />
          <ReferenceLine y={7.5} stroke={cssVar('--color-chart-axis')} strokeDasharray="4 4" strokeOpacity={0.15} />
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
    </section>
  );
}
