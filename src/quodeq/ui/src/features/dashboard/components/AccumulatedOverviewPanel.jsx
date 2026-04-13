import { useMemo } from 'react';
import DimensionViolationsRow from './DimensionViolationsRow.jsx';
import TrendBadge from '../../../components/TrendBadge.jsx';
import DimensionCardsGrid from './DimensionCardsGrid.jsx';
import { formatRunId, scoreColorClass, complianceRatio } from '../../../utils/formatters.js';
import { sortDimensionsByViolationSeverity } from '../../../utils/dimensionUtils.js';
import { collapseByDay, collectDayDimensions } from '../../../utils/dailyGrouping.js';
import RunHistoryPanel from './RunHistoryPanel.jsx';
import DimensionScorePanel from './DimensionScorePanel.jsx';
import ScoreCircle from '../../../components/ScoreCircle.jsx';
import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';
import { filterTrendByVisibleStandardsDaily, filterAccumulatedByVisibleStandards } from '../../../utils/scoreFiltering.js';
import CopyButton, { FileTextIcon } from '../../../components/CopyButton.jsx';
import { copyToClipboard } from '../../../utils/clipboard.js';
import { buildOverviewReport } from '../../../utils/reportBuilder.js';

// ---------------------------------------------------------------------------
// Accumulated overview panel helpers
// ---------------------------------------------------------------------------

function computeAccumulatedStats(accumulated, accumulatedDimensions, dailyTrend, selectedRunId) {
  const curr = parseFloat(accumulated?.summary?.numericAverage);
  // Derive delta from the selected run vs its predecessor in the trend
  let scoreDelta = null;
  if (dailyTrend && dailyTrend.length >= 2) {
    const selectedIdx = selectedRunId ? dailyTrend.findIndex((t) => t.runId === selectedRunId) : 0;
    const idx = selectedIdx >= 0 ? selectedIdx : 0;
    const current = parseFloat(dailyTrend[idx]?.numericAverage);
    const previous = idx + 1 < dailyTrend.length ? parseFloat(dailyTrend[idx + 1]?.numericAverage) : NaN;
    if (!isNaN(current) && !isNaN(previous)) scoreDelta = (current - previous).toFixed(1);
  }
  if (scoreDelta === null) {
    const prev = parseFloat(accumulated?.summary?.previousNumericAverage);
    scoreDelta = (isNaN(curr) || isNaN(prev)) ? null : (curr - prev).toFixed(1);
  }

  const withDates = accumulatedDimensions
    .filter((d) => d.fromRunId)
    .map((d) => ({ runId: d.fromRunId, dateISO: d.fromDateIso, dateLabel: d.fromDateLabel }));
  withDates.sort((a, b) => (b.dateISO || '').localeCompare(a.dateISO || ''));
  const lastRun = withDates.length === 0
    ? { date: null, runId: null }
    : { date: withDates[0].dateLabel || formatRunId(withDates[0].runId), runId: withDates[0].runId };

  const dimsWithViolations = sortDimensionsByViolationSeverity(accumulatedDimensions);
  const sorted = [...accumulatedDimensions].sort((a, b) => a.dimension.localeCompare(b.dimension));

  return { scoreDelta, lastRun, dimsWithViolations, sorted };
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SeverityTags({ severity }) {
  return (
    <div className="acc-eval-tags">
      {(severity?.critical || 0) > 0 && <span className="severity-tag critical">{severity.critical} critical</span>}
      {(severity?.major || 0) > 0 && <span className="severity-tag major">{severity.major} major</span>}
      {(severity?.minor || 0) > 0 && <span className="severity-tag minor">{severity.minor} minor</span>}
    </div>
  );
}

function AccumulatedHeroSection({ accumulated, scoreDelta, lastDate, accumulatedDimensions, projectName }) {
  const summary = accumulated?.summary;
  return (
    <section className="acc-eval-panel panel">
      <div className="acc-eval-top">
        <span className="acc-eval-label">Accumulated Evaluation</span>
        <div style={{ marginLeft: 'auto', display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
          <CopyButton
            label="Report"
            className="fix-plan-btn-header"
            icon={<FileTextIcon />}
            onClick={() => copyToClipboard(buildOverviewReport(accumulated, accumulatedDimensions || [], projectName))}
          />
          {lastDate && <span className="acc-eval-date">Last evaluated {lastDate}</span>}
        </div>
      </div>
      <div className="acc-eval-golden">
        <div className="acc-eval-circle-col">
          <ScoreCircle
            score={summary?.numericAverage}
            grade={summary?.overallGrade}
            size={120}
          />
          {scoreDelta !== null && (
            <div className="acc-eval-trend">
              <TrendBadge delta={scoreDelta} showLabel={false} />
            </div>
          )}
        </div>
        <div className="acc-eval-stats-col">
          <div className="acc-eval-stats-row">
            <div className="acc-eval-stat-block">
              <span className="acc-eval-stat-label">Violations</span>
              <span className="acc-eval-stat-value">{summary?.totalViolations || 0}</span>
              <SeverityTags severity={summary?.severity} />
            </div>
            <div className="acc-eval-stats-divider" />
            <div className="acc-eval-stat-block">
              <span className="acc-eval-stat-label">Ratio</span>
              <span className="acc-eval-stat-value">
                {complianceRatio(summary?.totalViolations || 0, summary?.totalCompliance || 0)}
              </span>
              <span className="acc-eval-ratio-sublabel">comp / viol</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function AccumulatedDimensionsSection({ sortedDimensions, onDimensionClick, dimensionsWithViolations, selectedDayDimNames }) {
  return (
    <>
      <div className="section-header">
        <h3 className="section-title">Quality Dimensions</h3>
      </div>
      <div className="dimensions-panel">
        <DimensionCardsGrid sortedDimensions={sortedDimensions} onDimensionClick={onDimensionClick} selectedDayDimNames={selectedDayDimNames} />
      </div>

      {dimensionsWithViolations.length > 0 && (
        <>
          <div className="section-header">
            <h3 className="section-title">Violations by Dimension</h3>
            <span className="section-count">
              {dimensionsWithViolations.length} dimensions analyzed
            </span>
          </div>
          <section className="panel violations-panel expandable">
            <div className="dimension-violations-list">
              {dimensionsWithViolations.map((dim) => (
                <DimensionViolationsRow
                  key={dim.dimension}
                  dimension={dim}
                  onClick={() => onDimensionClick(dim)}
                />
              ))}
            </div>
          </section>
        </>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Accumulated overview panel
// ---------------------------------------------------------------------------

function useAccumulatedComputations(data) {
  const { accumulated, accumulatedDimensions, availableRuns, dailyRuns, overviewRunIndex, trend, selectedRunId } = data;
  const dayRuns = dailyRuns || availableRuns;
  const dailyTrend = useMemo(() => collapseByDay(trend), [trend]);

  const effectiveSelectedId = useMemo(() => {
    if (!selectedRunId || !trend.length) return dailyTrend[0]?.runId || null;
    const direct = dailyTrend.find((t) => t.runId === selectedRunId);
    if (direct) return direct.runId;
    const rawEntry = trend.find((t) => t.runId === selectedRunId);
    if (rawEntry) {
      const datePart = (rawEntry.dateISO || '').slice(0, 10);
      const dayEntry = dailyTrend.find((t) => (t.dateISO || '').slice(0, 10) === datePart);
      if (dayEntry) return dayEntry.runId;
    }
    return dailyTrend[0]?.runId || null;
  }, [selectedRunId, trend, dailyTrend]);

  const currentOverviewRun = effectiveSelectedId || dayRuns[overviewRunIndex]?.runId || 'latest';
  const selectedDayDimNames = useMemo(
    () => collectDayDimensions(trend, currentOverviewRun) || collectDayDimensions(trend, selectedRunId),
    [trend, currentOverviewRun, selectedRunId]
  );

  const visibleIds = useMemo(() => readVisibleStandardIds(), [accumulatedDimensions]);
  const visibleSet = useMemo(() => new Set(visibleIds), [visibleIds]);
  const filteredDailyTrend = useMemo(() => filterTrendByVisibleStandardsDaily(trend, dailyTrend, visibleSet), [trend, dailyTrend, visibleSet]);
  const filteredDimensions = useMemo(() => accumulatedDimensions.filter((d) => visibleSet.has((d.dimension || '').toLowerCase())), [accumulatedDimensions, visibleIds]);
  const filteredAccumulated = useMemo(() => filterAccumulatedByVisibleStandards(accumulated, visibleSet, filteredDailyTrend, currentOverviewRun), [accumulated, visibleSet, filteredDailyTrend, currentOverviewRun]);
  const filteredStats = useMemo(() => computeAccumulatedStats(filteredAccumulated, filteredDimensions, filteredDailyTrend, currentOverviewRun), [filteredAccumulated, filteredDimensions, filteredDailyTrend, currentOverviewRun]);

  return { currentOverviewRun, selectedDayDimNames, filteredDailyTrend, filteredDimensions, filteredAccumulated, filteredStats };
}

export default function AccumulatedOverviewPanel({ data, callbacks }) {
  const { onRunClick, onDimensionClick } = callbacks;
  const { currentOverviewRun, selectedDayDimNames, filteredDailyTrend, filteredDimensions, filteredAccumulated, filteredStats } = useAccumulatedComputations(data);

  return (
    <>
      <AccumulatedHeroSection
        accumulated={filteredAccumulated}
        scoreDelta={filteredStats.scoreDelta}
        lastDate={filteredStats.lastRun.date}
        accumulatedDimensions={filteredDimensions}
        projectName={data.selectedProject}
      />

      <div className="history-panels-row">
        <RunHistoryPanel trend={filteredDailyTrend} selectedRunId={currentOverviewRun} onBarClick={onRunClick} />
        <DimensionScorePanel dimensions={filteredDimensions} onBarClick={onDimensionClick} runDate={filteredStats.lastRun.date} runId={filteredStats.lastRun.runId} />
      </div>

      <AccumulatedDimensionsSection
        sortedDimensions={filteredStats.sorted}
        onDimensionClick={onDimensionClick}
        dimensionsWithViolations={filteredStats.dimsWithViolations}
        selectedDayDimNames={selectedDayDimNames}
      />
    </>
  );
}
