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
// Accumulated overview panel
// Top-level panel component — prop count is intentional to avoid unnecessary
// indirection; each prop maps directly to a distinct piece of state or callback.
// ---------------------------------------------------------------------------

export default function AccumulatedOverviewPanel({ data, callbacks }) {
  const { accumulated, accumulatedDimensions, availableRuns, overviewRunIndex, trend, selectedRunId } = data;
  const { onRunClick, onDimensionClick, onFileClick, onPrincipleClick } = callbacks;

  const currentOverviewRun = availableRuns[overviewRunIndex]?.runId || 'latest';
  const referenceRun = overviewRunIndex === 0 ? availableRuns[0]?.runId : currentOverviewRun;

  const accumulatedTopFiles = useMemo(
    () => withDimensionsStr(buildTopOffendingFiles(accumulatedDimensions)),
    [accumulatedDimensions]
  );

  const accumulatedViolationsByPrinciple = useMemo(
    () =>
      accumulatedDimensions.flatMap((d) =>
        (d.violations || []).map((v) => ({ ...v, dimension: d.dimension }))
      ),
    [accumulatedDimensions]
  );

  const accumulatedScoreDelta = useMemo(() => {
    const curr = parseFloat(accumulated?.summary?.numericAverage);
    const prev = parseFloat(accumulated?.summary?.previousNumericAverage);
    if (isNaN(curr) || isNaN(prev)) return null;
    return (curr - prev).toFixed(1);
  }, [accumulated]);

  const accumulatedLastRun = useMemo(() => {
    // Find the most recent date using fromDateISO (already in API response)
    const withDates = accumulatedDimensions
      .filter((d) => d.fromRunId)
      .map((d) => ({ runId: d.fromRunId, dateISO: d.fromDateISO, dateLabel: d.fromDateLabel }));
    if (withDates.length === 0) return { date: null, runId: null };
    withDates.sort((a, b) => (b.dateISO || '').localeCompare(a.dateISO || ''));
    return {
      date: withDates[0].dateLabel || formatRunId(withDates[0].runId),
      runId: withDates[0].runId,
    };
  }, [accumulatedDimensions]);
  const accumulatedLastDate = accumulatedLastRun.date;

  const accumulatedUniquePrinciples = useMemo(
    () => new Set(accumulatedViolationsByPrinciple.map((v) => v.principle).filter(Boolean)).size,
    [accumulatedViolationsByPrinciple]
  );

  const dimensionsWithViolations = useMemo(
    () => sortDimensionsByViolationSeverity(accumulatedDimensions),
    [accumulatedDimensions]
  );

  const sortedDimensions = useMemo(
    () => [...accumulatedDimensions].sort((a, b) => a.dimension.localeCompare(b.dimension)),
    [accumulatedDimensions]
  );

  return (
    <>
      {/* Accumulated summary hero */}
      <section className="acc-eval-panel panel">
        <div className="acc-eval-top">
          <span className="acc-eval-label">Accumulated Evaluation</span>
          {accumulatedLastDate && (
            <span className="acc-eval-date">Last evaluated {accumulatedLastDate}</span>
          )}
        </div>

        <div className="acc-eval-hero">
          <span className={`acc-eval-grade-chip chip ${scoreColorClass(accumulated?.summary?.numericAverage)}`}>
            {accumulated?.summary?.overallGrade || '—'}</span>
          <div className="acc-eval-score-row">
            <span className="acc-eval-score">{accumulated?.summary?.numericAverage || '—'}</span>
            <span className="acc-eval-score-denom">/10</span>
          </div>
          {accumulatedScoreDelta !== null && (
            <div className="acc-eval-trend">
              <TrendBadge delta={accumulatedScoreDelta} showLabel={false} />
            </div>
          )}
        </div>

        <div className="acc-eval-stats-grid">
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Violations</span>
            <span className="acc-eval-stat-value">{accumulated?.summary?.totalViolations || 0}</span>
            <div className="acc-eval-tags">
              {(accumulated?.summary?.severity?.critical || 0) > 0 && <span className="severity-tag critical">{accumulated.summary.severity.critical} critical</span>}
              {(accumulated?.summary?.severity?.major || 0) > 0 && <span className="severity-tag major">{accumulated.summary.severity.major} major</span>}
              {(accumulated?.summary?.severity?.minor || 0) > 0 && <span className="severity-tag minor">{accumulated.summary.severity.minor} minor</span>}
            </div>
          </div>
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Compliance</span>
            <span className="acc-eval-stat-value">{accumulated?.summary?.totalCompliance || 0}</span>
          </div>
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Ratio</span>
            <span className="acc-eval-stat-value">
              {complianceRatio(accumulated?.summary?.totalViolations || 0, accumulated?.summary?.totalCompliance || 0)}
            </span>
          </div>
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Files Affected</span>
            <span className="acc-eval-stat-value">{accumulatedTopFiles.length}</span>
          </div>
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Principles</span>
            <span className="acc-eval-stat-value">{accumulatedUniquePrinciples}</span>
          </div>
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Dimensions</span>
            <span className="acc-eval-stat-value">{accumulated?.summary?.dimensionCount || 0}</span>
          </div>
        </div>
      </section>

      <div className="history-panels-row">
        <RunHistoryPanel
          trend={trend}
          selectedRunId={selectedRunId}
          selectedRunScore={accumulated?.summary?.numericAverage}
          onBarClick={onRunClick}
        />
        <DimensionScorePanel
          dimensions={accumulatedDimensions}
          onBarClick={onDimensionClick}
          runDate={accumulatedLastDate}
          runId={accumulatedLastRun.runId}
        />
      </div>

      {/* Quality dimension cards */}
      <div className="dimensions-header">
        <h3 className="dimensions-title">Quality Dimensions</h3>
      </div>
      <div className="dimensions-panel">
        <DimensionCardsGrid sortedDimensions={sortedDimensions} referenceRun={referenceRun} onDimensionClick={onDimensionClick} />
      </div>

      {/* Violations by dimension */}
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

      {/* Violations by file */}
      {accumulatedTopFiles.length > 0 && (
        <>
          <div className="section-header">
            <h3 className="section-title">Violations by File</h3>
            <span className="section-count">{accumulatedTopFiles.length} files</span>
          </div>
          <section className="panel wide-panel offending-panel">
            <div className="trend-table-wrap">
              <TopOffendingFilesTable
                files={accumulatedTopFiles}
                onFileClick={onFileClick}
              />
            </div>
          </section>
        </>
      )}

      {/* Violations by principle */}
      {accumulatedViolationsByPrinciple.length > 0 && (
        <>
          <div className="section-header">
            <h3 className="section-title">Violations by Principle</h3>
            <span className="section-count">{accumulatedUniquePrinciples} principles</span>
          </div>
          <section className="panel wide-panel offending-panel">
            <div className="trend-table-wrap">
              <ViolationsByPrincipleTable
                violations={accumulatedViolationsByPrinciple}
                onPrincipleClick={onPrincipleClick}
              />
            </div>
          </section>
        </>
      )}
    </>
  );
}
