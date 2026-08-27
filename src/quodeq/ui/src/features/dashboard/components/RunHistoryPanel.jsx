import { useState, useMemo } from 'react';
import { gradeLetter, formatPeriodLabel } from '../../../utils/formatters.js';
import { SectionLabel, PeriodSelect } from '../../../components/terminal/index.js';
import { t } from '../../../strings/index.js';
import { granularityLabel } from '../../../strings/labels.js';
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
import {
  cssVar,
  scoreBarColor,
  refLineValues,
  CHART_MARGIN,
  SELECTED_BAR_OPACITY,
  DESELECTED_BAR_OPACITY,
} from '../../../components/scoreChartHelpers.js';

const MAX_CHART_RUNS = 20;
const CHART_HEIGHT = 160;
const GRANULARITY_SUFFIX = {
  day: t('granularity.dayAbbrev'),
  week: t('granularity.weekAbbrev'),
  month: t('granularity.monthAbbrev'),
};


function buildTrendData(trend, selectedRunId, granularity = 'day') {
  return [...trend].slice(0, MAX_CHART_RUNS).reverse().map((row, i, arr) => {
    const numericAverage = parseFloat(row.numericAverage);
    return {
      ...row,
      numericAverage,
      periodLabel: formatPeriodLabel(row, granularity),
      delta: i > 0 ? numericAverage - parseFloat(arr[i - 1].numericAverage) : null,
    };
  });
}


// Every point here is the PROJECT grade -- the latest known score for each
// dimension, not the grade of that one scan. A scan that only measured
// clean-architecture still plots a full project number, which is what makes
// the line comparable across runs. The cost is that a point refreshed by 1 of
// 7 dimensions looks identical to one backed by a full sweep, so say when the
// refresh was partial. A complete scan needs no annotation.
export function RunHistoryTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const entry = payload[0]?.payload;
  if (!entry) return null;
  const score = Number.isFinite(entry.numericAverage) ? entry.numericAverage.toFixed(1) : '—';
  const grade = gradeLetter(entry.overallGrade);
  const refreshed = entry.dimensionsCount;
  const total = entry.accumulatedDimensionsCount;
  const partial = Number.isFinite(refreshed) && Number.isFinite(total) && refreshed < total;
  return (
    <div className="run-history-tooltip">
      <span className="rht-date">{entry.periodLabel || entry.dateLabel}</span>
      <span className="rht-score">{score} - {grade}</span>
      {partial && (
        <span className="rht-coverage">
          {t('history.partialRefresh', { count: refreshed, total })}
        </span>
      )}
    </div>
  );
}

function SelectedDot({ cx, cy, payload, selectedRunId }) {
  if (payload?.runId !== selectedRunId) return null;
  return <circle cx={cx} cy={cy} r={4} fill={cssVar('--color-chart-line')} stroke="white" strokeWidth={1.5} />;
}

function ScoreBars({ data, hoveredIndex, selectedRunId }) {
  // Click handling lives on the chart container (see ScoreHistoryChart).
  // The shared `.run-history-panel .recharts-surface *` CSS rule sets
  // pointer-events:none so the Area gradient cannot swallow clicks before
  // they reach the chart-level onClick handler.
  return (
    <Bar
      dataKey="numericAverage"
      radius={[0, 0, 0, 0]}
      maxBarSize={28}
      isAnimationActive={false}
    >
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
  );
}

function ScoreHistoryChart({ data, interaction }) {
  const { hoveredIndex, setHoveredIndex, selectedRunId, onBarClick } = interaction;
  // Hit-detection lives on the chart, not on the Bar: the <Area> gradient
  // and <Line> stroke layer on top of the bars and swallow click events
  // before they reach the Bar's onClick. The chart's onMouseMove and
  // onClick are dispatched on the container itself, so they fire wherever
  // you tap inside the chart and Recharts already computes the nearest
  // category as `activeTooltipIndex`.
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
    <ResponsiveContainer width="100%" height="100%" minHeight={CHART_HEIGHT}>
      <ComposedChart
        data={data}
        margin={CHART_MARGIN}
        onMouseMove={handleMove}
        onMouseLeave={() => setHoveredIndex(null)}
        onClick={onBarClick ? handleClick : undefined}
        style={onBarClick ? { cursor: 'pointer' } : undefined}
      >
        <defs>
          <linearGradient id="scoreAreaGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={cssVar('--color-accent')} stopOpacity={0.08} />
            <stop offset="100%" stopColor={cssVar('--color-accent')} stopOpacity={0} />
          </linearGradient>
        </defs>
        {/* Axes/grid/reference lines intentionally omitted — the mockup shows
            clean edge-to-edge bars with just the accent-coloured trend line
            on top. Labels live in the banner (MIN / MAX / AVG). */}
        <XAxis dataKey="dateLabel" hide />
        {/* One absolute 0-10 axis for everything: bar height means score
            (a 7 always fills 70%) and the line sits exactly on the bar
            tops. A zoomed line was tried twice and rejected both ways: a
            zoomed BAR reads as a smaller score, and a zoomed LINE visibly
            detaches from the bars. The shape stays subtle by design; the
            MIN/MAX/AVG banner carries the numbers. */}
        <YAxis domain={[0, 10]} hide />
        <Tooltip cursor={false} isAnimationActive={false} offset={20} content={<RunHistoryTooltip />} />
        {refLineValues([0, 10]).map((y, i) => (
          <ReferenceLine key={y} y={y} stroke={cssVar('--color-chart-axis')} strokeDasharray="4 4" strokeOpacity={i % 2 ? 0.2 : 0.3} />
        ))}
        <Area dataKey="numericAverage" type="monotone" fill="url(#scoreAreaGrad)" stroke="none" isAnimationActive={false} />
        <ScoreBars data={data} hoveredIndex={hoveredIndex} selectedRunId={selectedRunId} />
        <Line isAnimationActive={false} dataKey="numericAverage" type="monotone" stroke={cssVar('--color-accent')} strokeOpacity={0.9} strokeWidth={2} dot={<SelectedDot selectedRunId={selectedRunId} />} activeDot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export default function RunHistoryPanel({ trend = [], selectedRunId = null, onBarClick, granularity = 'day', onGranularityChange }) {
  const [hoveredIndex, setHoveredIndex] = useState(null);
  // Hooks must run in the same order every render, so compute before any early return.
  const data = useMemo(() => buildTrendData(trend, selectedRunId, granularity), [trend, selectedRunId, granularity]);

  // The parent only mounts this panel when there are ≥2 days of data, so an
  // empty trend shouldn't happen — but guard the truly-empty case. A single
  // bucket (e.g. all runs fall in one month) still renders the header so the
  // selector stays reachable; only the chart body + MIN/MAX/AVG are hidden.
  if (!trend || trend.length < 1) return null;

  const hasChart = data.length >= 2;
  const suffix = GRANULARITY_SUFFIX[granularity] || GRANULARITY_SUFFIX.day;
  let stats = null;
  if (hasChart) {
    // All-NaN buckets would make Math.min/max over an empty array yield
    // Infinity/-Infinity; skip the stats line entirely in that case.
    const valid = data.map((d) => d.numericAverage).filter((n) => !Number.isNaN(n));
    if (valid.length > 0) {
      const min = Math.min(...valid);
      const max = Math.max(...valid);
      const avg = valid.reduce((s, n) => s + n, 0) / valid.length;
      stats = t('overview.minMaxAvg', { min: min.toFixed(1), max: max.toFixed(1), avg: avg.toFixed(1) });
    }
  }

  return (
    <section className="run-history-panel run-history-panel--terminal panel" aria-label={t('overview.scoreHistoryAria')}>
      <div className="run-history-panel__header">
        <SectionLabel>{t('overview.scoreHistoryLabel')} · {data.length}{suffix}</SectionLabel>
        <span className="run-history-panel__controls">
          {onGranularityChange && <PeriodSelect value={granularity} onChange={onGranularityChange} />}
          {stats && <span className="run-history-panel__stats">{stats}</span>}
        </span>
      </div>
      {hasChart ? (
        <ScoreHistoryChart
          data={data}
          interaction={{ hoveredIndex, setHoveredIndex, selectedRunId, onBarClick }}
        />
      ) : (
        <p className="run-history-panel__sparse">{t('overview.sparseTrend', { period: granularityLabel(granularity) })}</p>
      )}
    </section>
  );
}
