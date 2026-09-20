import { useState, useMemo } from 'react';
import { gradeLetter, formatPeriodLabel } from '../../../utils/formatters.js';
import ChartKeyboardControls from '../../../components/ChartKeyboardControls.jsx';
import { t } from '../../../strings/index.js';
import { granularityLabel } from '../../../strings/labels.js';
import {
  ScoreHistoryChart,
  ScoreHistoryPanelFrame,
  ScoreTooltipCard,
  computeScoreStats,
  tooltipScore,
} from '../../../components/scoreChartParts.jsx';

const MAX_CHART_RUNS = 20;
const CHART_HEIGHT = 160;
const MAX_BAR_SIZE = 28;
// The chart needs two points before a trend line means anything.
const MIN_CHART_POINTS = 2;
const MISSING_SCORE = '—';
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
  const refreshed = entry.dimensionsCount;
  const total = entry.accumulatedDimensionsCount;
  const partial = Number.isFinite(refreshed) && Number.isFinite(total) && refreshed < total;
  return (
    <ScoreTooltipCard
      label={entry.periodLabel || entry.dateLabel}
      score={tooltipScore(entry.numericAverage, MISSING_SCORE)}
      grade={gradeLetter(entry.overallGrade)}
    >
      {partial && (
        <span className="rht-coverage">
          {t('history.partialRefresh', { count: refreshed, total })}
        </span>
      )}
    </ScoreTooltipCard>
  );
}

// Keyboard-only equivalent of the chart's mouse click: one focusable button
// per run, mirroring DimensionScoreHistoryPanel's own ChartKeyboardControls
// usage. Empty when there is nothing to click (ChartKeyboardControls itself
// renders null for an empty list).
// A bucket with no runId has nothing to select, so it gets no control rather
// than a button that calls onBarClick(undefined); the label follows the chart,
// which shows periodLabel once the granularity is week or month.
function buildRunKbdItems(data, onBarClick) {
  if (!onBarClick) return [];
  return data.filter((d) => d.runId).map((d) => ({
    key: d.runId,
    text: t('dashboard.runKbdItem', {
      date: d.periodLabel || d.dateLabel,
      score: tooltipScore(d.numericAverage, '?'),
    }),
    onActivate: () => onBarClick(d.runId),
  }));
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

  const hasChart = data.length >= MIN_CHART_POINTS;

  return (
    <ScoreHistoryPanelFrame
      ariaLabel={t('overview.scoreHistoryAria')}
      count={data.length}
      suffix={GRANULARITY_SUFFIX[granularity] || GRANULARITY_SUFFIX.day}
      granularity={granularity}
      onGranularityChange={onGranularityChange}
      stats={hasChart ? computeScoreStats(data) : null}
    >
      {hasChart ? (
        <div className="chart-with-kbd">
          <ScoreHistoryChart
            data={data}
            height={CHART_HEIGHT}
            fillHeight
            maxBarSize={MAX_BAR_SIZE}
            gradientId="scoreAreaGrad"
            tooltip={<RunHistoryTooltip />}
            showSelectedDot
            hoveredIndex={hoveredIndex}
            setHoveredIndex={setHoveredIndex}
            selectedRunId={selectedRunId}
            onActivate={onBarClick ? (point) => onBarClick(point.runId) : undefined}
          />
          <ChartKeyboardControls
            label={t('dashboard.runHistoryKbdLabel')}
            items={buildRunKbdItems(data, onBarClick)}
          />
        </div>
      ) : (
        <p className="run-history-panel__sparse">{t('overview.sparseTrend', { period: granularityLabel(granularity) })}</p>
      )}
    </ScoreHistoryPanelFrame>
  );
}
