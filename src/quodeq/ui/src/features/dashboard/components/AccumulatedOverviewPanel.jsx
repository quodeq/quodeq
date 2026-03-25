import { useMemo } from 'react';
import DimensionViolationsRow from './DimensionViolationsRow.jsx';
import TopOffendingFilesTable from './TopOffendingFilesTable.jsx';
import ViolationsByPrincipleTable from './ViolationsByPrincipleTable.jsx';
import TrendBadge from '../../../components/TrendBadge.jsx';
import DimensionCardsGrid from './DimensionCardsGrid.jsx';
import { buildTopOffendingFiles } from '../../../utils/explorerUtils.js';
import { formatRunId, scoreColorClass, complianceRatio } from '../../../utils/formatters.js';
import { withDimensionsStr, sortDimensionsByViolationSeverity } from '../../../utils/dimensionUtils.js';
import RunHistoryPanel from './RunHistoryPanel.jsx';
import DimensionScorePanel from './DimensionScorePanel.jsx';

// ---------------------------------------------------------------------------
// Accumulated overview panel helpers
// ---------------------------------------------------------------------------

function computeAccumulatedStats(accumulated, accumulatedDimensions) {
  const topFiles = withDimensionsStr(buildTopOffendingFiles(accumulatedDimensions));

  const violationsByPrinciple = accumulatedDimensions.flatMap((d) =>
    (d.violations || []).map((v) => ({ ...v, dimension: d.dimension }))
  );

  const curr = parseFloat(accumulated?.summary?.numericAverage);
  const prev = parseFloat(accumulated?.summary?.previousNumericAverage);
  const scoreDelta = (isNaN(curr) || isNaN(prev)) ? null : (curr - prev).toFixed(1);

  const withDates = accumulatedDimensions
    .filter((d) => d.fromRunId)
    .map((d) => ({ runId: d.fromRunId, dateISO: d.fromDateISO, dateLabel: d.fromDateLabel }));
  withDates.sort((a, b) => (b.dateISO || '').localeCompare(a.dateISO || ''));
  const lastRun = withDates.length === 0
    ? { date: null, runId: null }
    : { date: withDates[0].dateLabel || formatRunId(withDates[0].runId), runId: withDates[0].runId };

  const uniquePrinciples = new Set(violationsByPrinciple.map((v) => v.principle).filter(Boolean)).size;
  const dimsWithViolations = sortDimensionsByViolationSeverity(accumulatedDimensions);
  const sorted = [...accumulatedDimensions].sort((a, b) => a.dimension.localeCompare(b.dimension));

  return { topFiles, violationsByPrinciple, scoreDelta, lastRun, uniquePrinciples, dimsWithViolations, sorted };
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

function AccumulatedDimensionsSection({ sortedDimensions, referenceRun, onDimensionClick, dimensionsWithViolations, selectedDayDate }) {
  return (
    <>
      <div className="dimensions-header">
        <h3 className="dimensions-title">Quality Dimensions</h3>
      </div>
      <div className="dimensions-panel">
        <DimensionCardsGrid sortedDimensions={sortedDimensions} referenceRun={referenceRun} onDimensionClick={onDimensionClick} selectedDayDate={selectedDayDate} />
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

function AccumulatedDetailsSection({ topFiles, violationsByPrinciple, uniquePrinciples, onFileClick, onPrincipleClick }) {
  return (
    <>
      {topFiles.length > 0 && (
        <>
          <div className="section-header">
            <h3 className="section-title">Violations by File</h3>
            <span className="section-count">{topFiles.length} files</span>
          </div>
          <section className="panel wide-panel offending-panel">
            <div className="trend-table-wrap">
              <TopOffendingFilesTable files={topFiles} onFileClick={onFileClick} />
            </div>
          </section>
        </>
      )}

      {violationsByPrinciple.length > 0 && (
        <>
          <div className="section-header">
            <h3 className="section-title">Violations by Principle</h3>
            <span className="section-count">{uniquePrinciples} principles</span>
          </div>
          <section className="panel wide-panel offending-panel">
            <div className="trend-table-wrap">
              <ViolationsByPrincipleTable violations={violationsByPrinciple} onPrincipleClick={onPrincipleClick} />
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

function collapseByDay(trend) {
  // trend is newest-first. For each day, keep the FIRST (newest) entry
  // which has the most up-to-date accumulated state.
  // Collect dayDimensions from all runs of that day.
  if (!trend || trend.length === 0) return trend;
  const collapsed = [];
  let currentDay = null;
  let dayDims = new Set();
  let dayDimDetails = {};
  for (const entry of trend) {
    const datePart = (entry.dateISO || '').slice(0, 10);
    if (datePart !== currentDay) {
      if (currentDay !== null && collapsed.length > 0) {
        collapsed[collapsed.length - 1].dayDimensions = [...dayDims].sort();
        collapsed[collapsed.length - 1].dayDimensionDetails = Object.values(dayDimDetails).sort((a, b) => (a.dimension || '').localeCompare(b.dimension || ''));
      }
      currentDay = datePart;
      dayDims = new Set();
      dayDimDetails = {};
      collapsed.push({ ...entry }); // first (newest) entry of the day wins
    }
    // Don't replace — just collect dimensions from all runs of this day
    for (const d of entry.dimensions || []) dayDims.add(d);
    for (const d of entry.dimensionDetails || []) {
      if (!dayDimDetails[d.dimension || '']) dayDimDetails[d.dimension || ''] = d; // first (newest) wins
    }
  }
  if (collapsed.length > 0) {
    collapsed[collapsed.length - 1].dayDimensions = [...dayDims].sort();
    collapsed[collapsed.length - 1].dayDimensionDetails = Object.values(dayDimDetails).sort((a, b) => (a.dimension || '').localeCompare(b.dimension || ''));
  }
  return collapsed;
}

export default function AccumulatedOverviewPanel({ data, callbacks }) {
  const { accumulated, accumulatedDimensions, availableRuns, dailyRuns, overviewRunIndex, trend, selectedRunId } = data;
  const dayRuns = dailyRuns || availableRuns;
  const { onRunClick, onDimensionClick, onFileClick, onPrincipleClick } = callbacks;

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

  // Get the selected day's date for highlighting dimension cards.
  // Each accumulated dimension has fromDateISO — if it matches the selected day, it was evaluated that day.
  const selectedDayDate = useMemo(() => {
    const entry = trend.find((t) => t.runId === currentOverviewRun) || trend.find((t) => t.runId === selectedRunId);
    return (entry?.dateISO || '').slice(0, 10) || null;
  }, [trend, currentOverviewRun, selectedRunId]);

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
        topFilesCount={stats.topFiles.length}
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
        selectedDayDate={selectedDayDate}
      />

      <AccumulatedDetailsSection
        topFiles={stats.topFiles}
        violationsByPrinciple={stats.violationsByPrinciple}
        uniquePrinciples={stats.uniquePrinciples}
        onFileClick={onFileClick}
        onPrincipleClick={onPrincipleClick}
      />
    </>
  );
}
