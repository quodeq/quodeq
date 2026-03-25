import { useMemo } from 'react';
import DimensionViolationsRow from './DimensionViolationsRow.jsx';
import TrendBadge from '../../../components/TrendBadge.jsx';
import DimensionCardsGrid from './DimensionCardsGrid.jsx';
import { formatRunId, scoreColorClass, complianceRatio } from '../../../utils/formatters.js';
import { sortDimensionsByViolationSeverity } from '../../../utils/dimensionUtils.js';
import { collapseByDay, collectDayDimensions } from '../../../utils/dailyGrouping.js';
import RunHistoryPanel from './RunHistoryPanel.jsx';
import DimensionScorePanel from './DimensionScorePanel.jsx';

// ---------------------------------------------------------------------------
// Accumulated overview panel helpers
// ---------------------------------------------------------------------------

function computeAccumulatedStats(accumulated, accumulatedDimensions) {
  const curr = parseFloat(accumulated?.summary?.numericAverage);
  const prev = parseFloat(accumulated?.summary?.previousNumericAverage);
  const scoreDelta = (isNaN(curr) || isNaN(prev)) ? null : (curr - prev).toFixed(1);

  const withDates = accumulatedDimensions
    .filter((d) => d.fromRunId)
    .map((d) => ({ runId: d.fromRunId, dateISO: d.fromDateIso, dateLabel: d.fromDateLabel }));
  withDates.sort((a, b) => (b.dateISO || '').localeCompare(a.dateISO || ''));
  const lastRun = withDates.length === 0
    ? { date: null, runId: null }
    : { date: withDates[0].dateLabel || formatRunId(withDates[0].runId), runId: withDates[0].runId };

  const allViolations = accumulatedDimensions.flatMap((d) => d.violations || []);
  const uniqueFiles = new Set(allViolations.map((v) => v.file).filter(Boolean)).size;
  const uniquePrinciples = new Set(allViolations.map((v) => v.principle).filter(Boolean)).size;

  const dimsWithViolations = sortDimensionsByViolationSeverity(accumulatedDimensions);
  const sorted = [...accumulatedDimensions].sort((a, b) => a.dimension.localeCompare(b.dimension));

  return { scoreDelta, lastRun, uniqueFiles, uniquePrinciples, dimsWithViolations, sorted };
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatBlock({ label, value, children }) {
  return (
    <div className="acc-eval-stat-block">
      <span className="acc-eval-stat-label">{label}</span>
      <span className="acc-eval-stat-value">{value}</span>
      {children}
    </div>
  );
}

function SeverityTags({ severity }) {
  return (
    <div className="acc-eval-tags">
      {(severity?.critical || 0) > 0 && <span className="severity-tag critical">{severity.critical} critical</span>}
      {(severity?.major || 0) > 0 && <span className="severity-tag major">{severity.major} major</span>}
      {(severity?.minor || 0) > 0 && <span className="severity-tag minor">{severity.minor} minor</span>}
    </div>
  );
}

function AccumulatedHeroSection({ accumulated, scoreDelta, lastDate, topFilesCount, uniquePrinciples }) {
  const summary = accumulated?.summary;
  return (
    <section className="acc-eval-panel panel">
      <div className="acc-eval-top">
        <span className="acc-eval-label">Accumulated Evaluation</span>
        {lastDate && <span className="acc-eval-date">Last evaluated {lastDate}</span>}
      </div>
      <div className="acc-eval-hero">
        <span className={`acc-eval-grade-chip chip ${scoreColorClass(summary?.numericAverage)}`}>
          {summary?.overallGrade || '—'}</span>
        <div className="acc-eval-score-row">
          <span className="acc-eval-score">{summary?.numericAverage || '—'}</span>
          <span className="acc-eval-score-denom">/10</span>
        </div>
        {scoreDelta !== null && <div className="acc-eval-trend"><TrendBadge delta={scoreDelta} showLabel={false} /></div>}
      </div>
      <div className="acc-eval-stats-grid">
        <StatBlock label="Violations" value={summary?.totalViolations || 0}>
          <SeverityTags severity={summary?.severity} />
        </StatBlock>
        <StatBlock label="Compliance" value={summary?.totalCompliance || 0} />
        <StatBlock label="Ratio" value={complianceRatio(summary?.totalViolations || 0, summary?.totalCompliance || 0)} />
        <StatBlock label="Files Affected" value={topFilesCount} />
        <StatBlock label="Principles" value={uniquePrinciples} />
        <StatBlock label="Dimensions" value={summary?.dimensionCount || 0} />
      </div>
    </section>
  );
}

function AccumulatedDimensionsSection({ sortedDimensions, referenceRun, onDimensionClick, dimensionsWithViolations, selectedDayDimNames }) {
  return (
    <>
      <div className="dimensions-header">
        <h3 className="dimensions-title">Quality Dimensions</h3>
      </div>
      <div className="dimensions-panel">
        <DimensionCardsGrid sortedDimensions={sortedDimensions} referenceRun={referenceRun} onDimensionClick={onDimensionClick} selectedDayDimNames={selectedDayDimNames} />
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

export default function AccumulatedOverviewPanel({ data, callbacks }) {
  const { accumulated, accumulatedDimensions, availableRuns, dailyRuns, overviewRunIndex, trend, selectedRunId } = data;
  const dayRuns = dailyRuns || availableRuns;
  const { onRunClick, onDimensionClick } = callbacks;

  const dailyTrend = useMemo(() => collapseByDay(trend), [trend]);

  // Find which daily entry matches the current selection
  // selectedRunId may be any runId — find the day it belongs to
  const effectiveSelectedId = useMemo(() => {
    if (!selectedRunId || !trend.length) return dailyTrend[0]?.runId || null;
    // Check if selectedRunId is directly a daily entry
    const direct = dailyTrend.find((t) => t.runId === selectedRunId);
    if (direct) return direct.runId;
    // Find which raw trend entry matches, then find its day
    const rawEntry = trend.find((t) => t.runId === selectedRunId);
    if (rawEntry) {
      const datePart = (rawEntry.dateISO || '').slice(0, 10);
      const dayEntry = dailyTrend.find((t) => (t.dateISO || '').slice(0, 10) === datePart);
      if (dayEntry) return dayEntry.runId;
    }
    return dailyTrend[0]?.runId || null;
  }, [selectedRunId, trend, dailyTrend]);

  const currentOverviewRun = effectiveSelectedId || dayRuns[overviewRunIndex]?.runId || 'latest';
  const referenceRun = overviewRunIndex === 0 ? dayRuns[0]?.runId : currentOverviewRun;

  const selectedDayDimNames = useMemo(
    () => collectDayDimensions(trend, currentOverviewRun) || collectDayDimensions(trend, selectedRunId),
    [trend, currentOverviewRun, selectedRunId]
  );

  const stats = useMemo(
    () => computeAccumulatedStats(accumulated, accumulatedDimensions),
    [accumulated, accumulatedDimensions]
  );

  return (
    <>
      <AccumulatedHeroSection
        accumulated={accumulated}
        scoreDelta={stats.scoreDelta}
        lastDate={stats.lastRun.date}
        topFilesCount={stats.uniqueFiles}
        uniquePrinciples={stats.uniquePrinciples}
      />

      <div className="history-panels-row">
        <RunHistoryPanel trend={dailyTrend} selectedRunId={currentOverviewRun} selectedRunScore={accumulated?.summary?.numericAverage} onBarClick={onRunClick} />
        <DimensionScorePanel dimensions={accumulatedDimensions} onBarClick={onDimensionClick} runDate={stats.lastRun.date} runId={stats.lastRun.runId} />
      </div>

      <AccumulatedDimensionsSection
        sortedDimensions={stats.sorted}
        referenceRun={referenceRun}
        onDimensionClick={onDimensionClick}
        dimensionsWithViolations={stats.dimsWithViolations}
        selectedDayDimNames={selectedDayDimNames}
      />

    </>
  );
}
