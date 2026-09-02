import { useMemo } from 'react';
import { collapseByPeriod, collectPeriodDimensions, bucketKey, extractDimensionPeriodSeries, sliceTrendAtRun } from '../../../utils/dailyGrouping.js';
import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';
import { filterTrendByVisibleStandards, filterTrendByVisibleStandardsDaily, filterAccumulatedByVisibleStandards } from '../../../utils/scoreFiltering.js';
import { formatRunId } from '../../../utils/formatters.js';

// Sparkline history length for the per-dimension period series (matches the
// old DimensionScorePanel SPARKLINE_LIMIT).
const DIM_SPARKLINE_LIMIT = 10;

// The "vs previous" delta compares two accumulated numericAverage points from the
// trend (this run vs the prior run). With fewer than two trend entries there is no
// comparable previous point, so the delta stays null rather than falling back to
// summary.previousNumericAverage: that value is the prior run's own-dimension average,
// not comparable to the accumulated numericAverage (an apples-to-oranges subtraction).
// Canonical definition lives here (not in AccumulatedOverviewPanel.jsx, which
// re-exports it) to avoid a circular import: this hook needs it too.
export function computeAccumulatedStats(accumulatedDimensions, dailyTrend, selectedRunId) {
  let scoreDelta = null;
  if (dailyTrend && dailyTrend.length >= 2) {
    const selectedIdx = selectedRunId ? dailyTrend.findIndex((t) => t.runId === selectedRunId) : 0;
    const idx = selectedIdx >= 0 ? selectedIdx : 0;
    const current = parseFloat(dailyTrend[idx]?.numericAverage);
    const previous = idx + 1 < dailyTrend.length ? parseFloat(dailyTrend[idx + 1]?.numericAverage) : NaN;
    if (!Number.isNaN(current) && !Number.isNaN(previous)) scoreDelta = (current - previous).toFixed(1);
  }

  const withDates = accumulatedDimensions
    .filter((d) => d.fromRunId)
    .map((d) => ({ runId: d.fromRunId, dateISO: d.fromDateIso, dateLabel: d.fromDateLabel }));
  withDates.sort((a, b) => (b.dateISO || '').localeCompare(a.dateISO || ''));
  const lastRun = withDates.length === 0
    ? { date: null, runId: null }
    : { date: withDates[0].dateLabel || formatRunId(withDates[0].runId), runId: withDates[0].runId };

  const sorted = [...accumulatedDimensions].sort((a, b) => a.dimension.localeCompare(b.dimension));

  return { scoreDelta, lastRun, sorted };
}

// Which run the Overview is currently showing: the trend entry matching
// selectedRunId if the period-collapse still has it (directly, or via its
// day's bucket), else the period's most recent entry, else the day-runs
// index as a last resort.
function useOverviewRunSelection({ trend, periodTrend, dayRuns, overviewRunIndex, selectedRunId, granularity }) {
  const effectiveSelectedId = useMemo(() => {
    if (!selectedRunId || !trend.length) return periodTrend[0]?.runId || null;
    const direct = periodTrend.find((t) => t.runId === selectedRunId);
    if (direct) return direct.runId;
    const rawEntry = trend.find((t) => t.runId === selectedRunId);
    if (rawEntry) {
      const key = bucketKey(rawEntry.dateISO, granularity);
      const bucketEntry = periodTrend.find((t) => bucketKey(t.dateISO, granularity) === key);
      if (bucketEntry) return bucketEntry.runId;
    }
    return periodTrend[0]?.runId || null;
  }, [selectedRunId, trend, periodTrend, granularity]);

  const currentOverviewRun = effectiveSelectedId || dayRuns[overviewRunIndex]?.runId || 'latest';
  const selectedDayDimNames = useMemo(
    () => collectPeriodDimensions(trend, currentOverviewRun, granularity) || collectPeriodDimensions(trend, selectedRunId, granularity),
    [trend, currentOverviewRun, selectedRunId, granularity]
  );
  return { currentOverviewRun, selectedDayDimNames };
}

// Period-aware per-dimension trends: one entry per visible dimension,
// { delta, scores }, bucketed by the selected granularity from the raw
// (visible-filtered, per-run) trend. Feeds both the dimension cards and
// the DIMENSIONS panel so their deltas/sparklines match the Overview chart.
// The trend is sliced at the selected overview run first, so navigating to
// a previous period truncates the series at that point in time — arrows
// and sparklines then agree with the as-of scores on the cards. The delta
// compares the last two buckets in which the dimension has data (carry-over
// semantics, same as the dimmed cards).
function useDimTrends(filteredDimensions, filteredTrend, currentOverviewRun, granularity) {
  const asOfTrend = useMemo(
    () => sliceTrendAtRun(filteredTrend, currentOverviewRun),
    [filteredTrend, currentOverviewRun]
  );
  return useMemo(() => {
    const map = {};
    for (const dim of filteredDimensions) {
      const name = dim.dimension || '';
      const series = extractDimensionPeriodSeries(asOfTrend, name, granularity, DIM_SPARKLINE_LIMIT);
      const scores = series.map((s) => s.score);
      const delta = scores.length >= 2 ? scores[scores.length - 1] - scores[scores.length - 2] : null;
      map[name.toLowerCase()] = { delta, scores };
    }
    return map;
  }, [filteredDimensions, asOfTrend, granularity]);
}

export function useAccumulatedComputations(data) {
  const { accumulated, accumulatedDimensions, availableRuns, dailyRuns, overviewRunIndex, trend, selectedRunId, granularity = 'day' } = data;
  const dayRuns = dailyRuns || availableRuns;
  const dayTrend = useMemo(() => collapseByPeriod(trend, 'day'), [trend]);
  const periodTrend = useMemo(() => collapseByPeriod(trend, granularity), [trend, granularity]);

  const { currentOverviewRun, selectedDayDimNames } = useOverviewRunSelection({ trend, periodTrend, dayRuns, overviewRunIndex, selectedRunId, granularity });

  const visibleIds = useMemo(() => readVisibleStandardIds(), [accumulatedDimensions]);
  const visibleSet = useMemo(() => new Set(visibleIds), [visibleIds]);
  const filteredDayTrend = useMemo(() => filterTrendByVisibleStandardsDaily(trend, dayTrend, visibleSet, 'day'), [trend, dayTrend, visibleSet]);
  const filteredPeriodTrend = useMemo(() => filterTrendByVisibleStandardsDaily(trend, periodTrend, visibleSet, granularity), [trend, periodTrend, visibleSet, granularity]);
  // Raw (per-run) filtered trend — sparklines show every evaluation, not the
  // period-collapsed representatives.
  const filteredTrend = useMemo(() => filterTrendByVisibleStandards(trend, visibleSet), [trend, visibleSet]);
  const filteredDimensions = useMemo(() => accumulatedDimensions.filter((d) => visibleSet.has((d.dimension || '').toLowerCase())), [accumulatedDimensions, visibleIds]);

  const dimTrends = useDimTrends(filteredDimensions, filteredTrend, currentOverviewRun, granularity);
  const filteredAccumulated = useMemo(() => filterAccumulatedByVisibleStandards(accumulated, visibleSet, filteredPeriodTrend, currentOverviewRun), [accumulated, visibleSet, filteredPeriodTrend, currentOverviewRun]);
  const filteredStats = useMemo(() => computeAccumulatedStats(filteredDimensions, filteredPeriodTrend, currentOverviewRun), [filteredDimensions, filteredPeriodTrend, currentOverviewRun]);

  // Preserve today's "panel appears iff ≥2 days of data" behavior, regardless
  // of the chosen grouping — so the selector never disappears on collapse.
  const chartMountable = filteredDayTrend.length >= 2;

  return { currentOverviewRun, selectedDayDimNames, filteredPeriodTrend, filteredTrend, filteredDimensions, filteredAccumulated, filteredStats, chartMountable, dimTrends };
}
