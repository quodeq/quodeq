import { useMemo, useState } from 'react';
import {
  ComposedChart,
  Area,
  Bar,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
} from 'recharts';
import { SectionLabel } from '../../../components/terminal/index.js';
import { gradeLetter } from '../../../utils/formatters.js';
import ChartKeyboardControls from '../../../components/ChartKeyboardControls.jsx';
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

const MAX = 16;
const CHART_HEIGHT = 160;

/**
 * Build chart data points for a single dimension's history.
 * Walks the trend (newest-first) and emits one point per run that
 * scored this dimension, oldest-first to read left-to-right.
 */
function buildDimensionData(trend, dimensionName, limit) {
  if (!Array.isArray(trend) || !dimensionName) return [];
  const want = String(dimensionName).toLowerCase();
  const points = [];
  for (const entry of trend) {
    const details = entry?.dimensionDetails;
    if (!Array.isArray(details)) continue;
    const match = details.find((d) => (d.dimension || '').toLowerCase() === want);
    const score = match ? parseFloat(match.score) : NaN;
    if (!Number.isFinite(score)) continue;
    points.push({
      runId: entry.runId,
      dateLabel: entry.dateLabel,
      numericAverage: score,
      overallGrade: match.grade ?? entry.overallGrade,
    });
    if (points.length >= limit) break;
  }
  return points.reverse();
}

function DimensionTooltip({ active, payload }) {
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

function SelectedDot({ cx, cy, payload, selectedRunId }) {
  if (payload?.runId !== selectedRunId) return null;
  return <circle cx={cx} cy={cy} r={4} fill={cssVar('--color-chart-line')} stroke="white" strokeWidth={1.5} />;
}

function DimensionHistoryChart({ data, selectedRunId, hoveredIndex, setHoveredIndex, onBarClick }) {
  const handleClick = (state) => {
    const idx = state?.activeTooltipIndex;
    if (idx == null) return;
    const point = data[idx];
    if (point?.runId) onBarClick?.(point);
  };
  return (
    <ResponsiveContainer width="100%" height="100%" minHeight={CHART_HEIGHT}>
      <ComposedChart
        data={data}
        margin={CHART_MARGIN}
        onMouseMove={(state) => setHoveredIndex(state?.activeTooltipIndex ?? null)}
        onMouseLeave={() => setHoveredIndex(null)}
        onClick={onBarClick ? handleClick : undefined}
        style={onBarClick ? { cursor: 'pointer' } : undefined}
      >
        <defs>
          <linearGradient id="dimScoreAreaGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={cssVar('--color-accent')} stopOpacity={0.08} />
            <stop offset="100%" stopColor={cssVar('--color-accent')} stopOpacity={0} />
          </linearGradient>
        </defs>
        <XAxis dataKey="dateLabel" hide />
        <YAxis domain={[0, 10]} hide />
        <Tooltip cursor={false} isAnimationActive={false} offset={20} content={<DimensionTooltip />} />
        <ReferenceLine y={REF_LINE_LOW}  stroke={cssVar('--color-chart-axis')} strokeDasharray="4 4" strokeOpacity={0.45} />
        <ReferenceLine y={REF_LINE_MID}  stroke={cssVar('--color-chart-axis')} strokeDasharray="4 4" strokeOpacity={0.45} />
        <ReferenceLine y={REF_LINE_HIGH} stroke={cssVar('--color-chart-axis')} strokeDasharray="4 4" strokeOpacity={0.45} />
        <Area dataKey="numericAverage" type="monotone" fill="url(#dimScoreAreaGrad)" stroke="none" isAnimationActive={false} />
        <Bar dataKey="numericAverage" radius={[0, 0, 0, 0]} maxBarSize={28} isAnimationActive={false}>
          {data.map((entry, i) => (
            <Cell
              key={entry.runId ?? i}
              fill={scoreBarColor(entry.numericAverage)}
              opacity={entry.runId === selectedRunId ? SELECTED_BAR_OPACITY : DESELECTED_BAR_OPACITY}
              stroke={hoveredIndex === i ? cssVar('--color-chart-stroke') : 'none'}
              strokeWidth={hoveredIndex === i ? 1.5 : 0}
            />
          ))}
        </Bar>
        <Line
          isAnimationActive={false}
          dataKey="numericAverage"
          type="monotone"
          stroke={cssVar('--color-accent')}
          strokeOpacity={0.9}
          strokeWidth={2}
          dot={<SelectedDot selectedRunId={selectedRunId} />}
          activeDot={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export default function DimensionScoreHistoryPanel({ trend = [], dimension, selectedRunId = null, onBarClick }) {
  const [hoveredIndex, setHoveredIndex] = useState(null);
  const data = useMemo(() => buildDimensionData(trend, dimension, MAX), [trend, dimension]);

  const stats = useMemo(() => {
    const scores = data.map((d) => d.numericAverage).filter(Number.isFinite);
    if (scores.length === 0) return null;
    return {
      min: Math.min(...scores),
      max: Math.max(...scores),
      avg: scores.reduce((s, n) => s + n, 0) / scores.length,
    };
  }, [data]);

  return (
    <section className="run-history-panel run-history-panel--terminal panel" aria-label={`${dimension} score history`}>
      <div className="run-history-panel__header">
        <SectionLabel>score_history · {data.length}d</SectionLabel>
        {stats && (
          <span className="run-history-panel__stats">
            MIN {stats.min.toFixed(1)} / MAX {stats.max.toFixed(1)} / AVG {stats.avg.toFixed(1)}
          </span>
        )}
      </div>
      {data.length === 0 ? (
        <div className="qd-history-empty">no history yet for this dimension</div>
      ) : (
        <div className="chart-with-kbd">
          <DimensionHistoryChart
            data={data}
            selectedRunId={selectedRunId}
            hoveredIndex={hoveredIndex}
            setHoveredIndex={setHoveredIndex}
            onBarClick={onBarClick}
          />
          <ChartKeyboardControls
            label={`${dimension} score history — Tab to a run, Enter to open it`}
            items={onBarClick ? data.map((d, i) => ({
              key: d.runId ?? i,
              text: `${d.dateLabel}: ${Number.isFinite(d.numericAverage) ? d.numericAverage.toFixed(1) : '?'}, grade ${gradeLetter(d.overallGrade)}${d.runId === selectedRunId ? ' (selected)' : ''}`,
              onActivate: () => onBarClick(d),
            })) : []}
          />
        </div>
      )}
    </section>
  );
}
