import { useState, useMemo } from 'react';
import { formatPeriodLabel } from '../../../utils/formatters.js';
import { t } from '../../../strings/index.js';
import { granularityLabel } from '../../../strings/labels.js';
import {
  ScoreChartWithKeyboard,
  ScoreHistoryPanelFrame,
  computeScoreStats,
  makeScoreTooltip,
  periodOrDateLabel,
  tooltipScore,
} from '../../../components/scoreChartPanel.jsx';
import { PANEL_CHART_HEIGHT_PX } from '../../../components/scoreChartHelpers.js';

const MAX_CHART_RUNS = 20;
const MAX_BAR_SIZE = 28;
// The chart needs two points before a trend line means anything.
const MIN_CHART_POINTS = 2;
const MISSING_SCORE = '—';
const GRANULARITY_SUFFIX = {
  day: t('granularity.dayAbbrev'),
  week: t('granularity.weekAbbrev'),
  month: t('granularity.monthAbbrev'),
};


function buildTrendData(trend, granularity = 'day') {
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
export const RunHistoryTooltip = makeScoreTooltip({
  label: periodOrDateLabel,
  missingScore: MISSING_SCORE,
  extra: (entry) => {
    const refreshed = entry.dimensionsCount;
    const total = entry.accumulatedDimensionsCount;
    if (!Number.isFinite(refreshed) || !Number.isFinite(total) || refreshed >= total) return null;
    return (
      <span className="rht-coverage">
        {t('history.partialRefresh', { count: refreshed, total })}
      </span>
    );
  },
});

const CHART_PRESENTATION = {
  height: PANEL_CHART_HEIGHT_PX,
  fillHeight: true,
  maxBarSize: MAX_BAR_SIZE,
  gradientId: 'scoreAreaGrad',
  tooltip: <RunHistoryTooltip />,
  showSelectedDot: true,
};

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
  const data = useMemo(() => buildTrendData(trend, granularity), [trend, granularity]);

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
        <ScoreChartWithKeyboard
          data={data}
          chart={CHART_PRESENTATION}
          interaction={{
            hoveredIndex,
            setHoveredIndex,
            selectedRunId,
            onActivate: onBarClick ? (point) => onBarClick(point.runId) : undefined,
          }}
          kbdLabel={t('dashboard.runHistoryKbdLabel')}
          kbdItems={buildRunKbdItems(data, onBarClick)}
        />
      ) : (
        <p className="run-history-panel__sparse">{t('overview.sparseTrend', { period: granularityLabel(granularity) })}</p>
      )}
    </ScoreHistoryPanelFrame>
  );
}
