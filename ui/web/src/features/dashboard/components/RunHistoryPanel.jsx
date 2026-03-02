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

const GRADE_VAR = {
  exemplary:    '--color-grade-top-text',
  good:         '--color-grade-high-text',
  proficient:   '--color-grade-high-text',
  adequate:     '--color-grade-mid-text',
  developing:   '--color-grade-mid-text',
  poor:         '--color-grade-low-text',
  insufficient: '--color-grade-low-text',
  critical:     '--color-grade-bottom-text',
  a: '--color-grade-top-text',
  b: '--color-grade-high-text',
  c: '--color-grade-mid-text',
  d: '--color-grade-low-text',
  f: '--color-grade-bottom-text',
};

function gradeBarColor(grade) {
  if (!grade) return cssVar('--color-accent', '#e8795a');
  const key = grade.trim().toLowerCase();
  const varName = GRADE_VAR[key] ?? GRADE_VAR[key.charAt(0)];
  return varName ? cssVar(varName, '#e8795a') : cssVar('--color-accent', '#e8795a');
}

// Trend direction — mirrors the logic in TrendBadge
const TREND_ARROW = { up: '↑', 'soft-up': '↗', same: '→', 'soft-down': '↘', down: '↓' };
const TREND_COLOR = {
  up:         '#5ee6a0',
  'soft-up':  '#92c9a8',
  same:       '#94a3b8',
  'soft-down':'#c8956c',
  down:       '#f09070',
};

function trendDir(delta) {
  if (delta === null || delta === undefined) return null;
  if (delta > 1)   return 'up';
  if (delta > 0.5) return 'soft-up';
  if (delta < -1)  return 'down';
  if (delta < -0.5) return 'soft-down';
  return 'same';
}

function RunHistoryTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="run-history-tooltip">
      <span className="rht-date">{d.dateLabel}</span>
      <span className="rht-score">{d.numericAverage.toFixed(1)} / 10</span>
      <span className="rht-grade">{d.overallGrade}</span>
    </div>
  );
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

  // Custom label above each bar: trend arrow + delta value below it
  const renderTrendLabel = ({ x, y, width, index }) => {
    const entry = data[index];
    const dir = trendDir(entry?.delta);
    if (!dir) return null;
    const cx = x + width / 2;
    const deltaStr = entry.delta > 0 ? `+${entry.delta.toFixed(1)}` : entry.delta.toFixed(1);
    return (
      <g>
        <text x={cx} y={y - 25} textAnchor="middle" fontSize={9} fill={TREND_COLOR[dir]}>
          {deltaStr}
        </text>
        <text x={cx} y={y - 14} textAnchor="middle" fontSize={11} fill={TREND_COLOR[dir]}>
          {TREND_ARROW[dir]}
        </text>
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
          <CartesianGrid vertical={false} stroke={cssVar('--color-border', '#383532')} />
          <XAxis
            dataKey="dateLabel"
            tick={{ fontSize: 11, fill: cssVar('--color-text-muted', '#9a9490') }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            domain={[0, 10]}
            ticks={[0, 2.5, 5, 7.5, 10]}
            tick={{ fontSize: 11, fill: cssVar('--color-text-muted', '#9a9490') }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={RunHistoryTooltip} cursor={false} isAnimationActive={false} />
          <ReferenceLine y={5} stroke={cssVar('--color-text-muted', '#9a9490')} strokeDasharray="4 4" strokeOpacity={0.5} />
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
                fill={gradeBarColor(entry.overallGrade)}
                opacity={entry.runId === selectedRunId ? 1 : 0.55}
                stroke={hoveredIndex === i ? 'rgba(255,255,255,0.25)' : 'none'}
                strokeWidth={hoveredIndex === i ? 1.5 : 0}
              />
            ))}
          </Bar>
          <Line
            isAnimationActive={false}
            dataKey="numericAverage"
            type="monotone"
            stroke={cssVar('--color-text-muted', '#9a9490')}
            strokeWidth={2.5}
            dot={{ r: 3, fill: cssVar('--color-text-muted', '#9a9490'), strokeWidth: 0 }}
            activeDot={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </section>
  );
}
