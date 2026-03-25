import { useMemo } from 'react';
import DimensionViolationsRow from './DimensionViolationsRow.jsx';
import TopOffendingFilesTable from './TopOffendingFilesTable.jsx';
import TrendBadge from '../../../components/TrendBadge.jsx';
import CopyButton from '../../../components/CopyButton.jsx';
import ScoreCircle from '../../../components/ScoreCircle.jsx';
import { copyToClipboard } from '../../../utils/clipboard.js';
import { buildTopOffendingFiles, buildDimensionPlanFromViolations } from '../../../utils/explorerUtils.js';
import { formatRunId, scoreColorClass, splitScore, complianceRatio } from '../../../utils/formatters.js';
import { withDimensionsStr, sortDimensionsByViolationSeverity } from '../../../utils/dimensionUtils.js';
import buildRunSummary from '../buildRunSummary.js';

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------


function ViolationsByDimension({ dimensionsWithViolations, onDimensionClick, selectedRunId }) {
  if (dimensionsWithViolations.length === 0) return null;
  return (
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
              onClick={() => onDimensionClick(dim, selectedRunId)}
            />
          ))}
        </div>
      </section>
    </>
  );
}

function RunDimensionCard({ item, selectedRunId, dateLabel, onDimensionClick }) {
  const currScore = parseFloat(item.overallScore);
  const prevScore = parseFloat(item.previousScore);
  const delta = !isNaN(currScore) && !isNaN(prevScore) ? currScore - prevScore : null;
  const scored = splitScore(item.overallScore);
  const gradeClass = scoreColorClass(currScore);
  return (
    <article
      key={item.dimension}
      className={`qd-card ${gradeClass}`}
      onClick={() => onDimensionClick(item, selectedRunId)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onDimensionClick(item, selectedRunId); } }}
    >
      <div className="qd-card-header">
        <span className="qd-card-name">{item.dimension}</span>
        <TrendBadge delta={delta} />
      </div>
      <div className="qd-card-columns">
        <div className="qd-card-col">
          <span className="qd-card-col-score">{scored.value}</span>
        </div>
        <div className="qd-card-col-divider" />
        <div className="qd-card-col">
          <span className="qd-card-col-label">Viol</span>
          <span className="qd-card-col-value">{item.totals?.violationCount ?? 0}</span>
        </div>
        <div className="qd-card-col-divider" />
        <div className="qd-card-col">
          <span className="qd-card-col-label">Ratio</span>
          <span className="qd-card-col-value">{complianceRatio(item.totals?.violationCount ?? 0, item.totals?.complianceCount ?? 0)}</span>
        </div>
      </div>
      <div className="qd-card-footer">
        <span className="qd-card-date">{item.fromDateLabel || dateLabel || formatRunId(item.fromRunId || selectedRunId)}</span>
      </div>
      <div className="qd-card-grade-bar" />
    </article>
  );
}

function RunDimensionsGrid({ dimensions, selectedRunId, dateLabel, onDimensionClick }) {
  return (
    <div className="dimensions-grid">
      {[...dimensions]
        .sort((a, b) => a.dimension.localeCompare(b.dimension))
        .map((item) => (
          <RunDimensionCard key={item.dimension} item={item} selectedRunId={selectedRunId} dateLabel={dateLabel} onDimensionClick={onDimensionClick} />
        ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Run-specific overview panel
// ---------------------------------------------------------------------------

function computeRunScoreDelta(dashboard) {
  const trendSeries = dashboard?.trend || [];
  const currentRunId = dashboard?.selectedRun?.runId;
  const idx = trendSeries.findIndex((t) => t.runId === currentRunId);
  if (idx < 0 || idx + 1 >= trendSeries.length) return null;
  const curr = parseFloat(trendSeries[idx].numericAverage);
  const prev = parseFloat(trendSeries[idx + 1].numericAverage);
  if (isNaN(curr) || isNaN(prev)) return null;
  return (curr - prev).toFixed(1);
}

function RunHeroSection({ dashboard, selectedRunId, stats }) {
  const { runSummary, runScoreDelta, runTopFiles, runUniquePrinciples } = stats;
  return (
    <section className="acc-eval-panel panel">
      <div className="acc-eval-top">
        <span className="acc-eval-date">{dashboard?.selectedRun?.dateLabel || formatRunId(selectedRunId)}</span>
        {(dashboard?.dimensions || []).some((d) => (d.violations?.length || 0) > 0) && (
          <CopyButton
            label="Fix plan"
            onClick={() => {
              const allViolations = (dashboard.dimensions || []).flatMap(
                (d) => (d.violations || []).map((v) => ({ ...v, dimension: d.dimension }))
              );
              copyToClipboard(buildDimensionPlanFromViolations(dashboard?.selectedRun?.dateLabel || formatRunId(selectedRunId), allViolations));
            }}
          />
        )}
      </div>
      <div className="acc-eval-golden">
        <div className="acc-eval-circle-col">
          <ScoreCircle
            score={runSummary.numericAverage}
            grade={runSummary.overallGrade}
            size={120}
          />
          {runScoreDelta !== null && (
            <div className="acc-eval-trend">
              <TrendBadge delta={runScoreDelta} showLabel={false} />
            </div>
          )}
        </div>
        <div className="acc-eval-stats-col">
          <div className="acc-eval-stats-row">
            <div className="acc-eval-stat-block">
              <span className="acc-eval-stat-label">Violations</span>
              <span className="acc-eval-stat-value">{runSummary.totalViolations || 0}</span>
              <div className="acc-eval-tags">
                {(runSummary.severity?.critical || 0) > 0 && <span className="severity-tag critical">{runSummary.severity.critical} crit</span>}
                {(runSummary.severity?.major || 0) > 0 && <span className="severity-tag major">{runSummary.severity.major} maj</span>}
                {(runSummary.severity?.minor || 0) > 0 && <span className="severity-tag minor">{runSummary.severity.minor} min</span>}
              </div>
            </div>
            <div className="acc-eval-stats-divider" />
            <div className="acc-eval-stat-block">
              <span className="acc-eval-stat-label">Ratio</span>
              <span className="acc-eval-stat-value">
                {complianceRatio(runSummary.totalViolations || 0, runSummary.totalCompliance || 0)}
              </span>
              <span className="acc-eval-ratio-sublabel">comp / viol</span>
            </div>
          </div>
          <div className="acc-eval-mini-stats">
            <div className="acc-eval-mini-stat">
              <span className="acc-eval-mini-stat-label">Files</span>
              <span className="acc-eval-mini-stat-value">{runTopFiles.length}</span>
            </div>
            <div className="acc-eval-mini-stat">
              <span className="acc-eval-mini-stat-label">Principles</span>
              <span className="acc-eval-mini-stat-value">{runUniquePrinciples}</span>
            </div>
            <div className="acc-eval-mini-stat">
              <span className="acc-eval-mini-stat-label">Dimensions</span>
              <span className="acc-eval-mini-stat-value">{runSummary.dimensionCount || 0}</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function RunFileViolations({ runTopFiles, onFileClick }) {
  if (runTopFiles.length === 0) return null;
  return (
    <>
      <div className="section-header">
        <h3 className="section-title">Violations by File</h3>
        <span className="section-count">{runTopFiles.length} files</span>
      </div>
      <section className="panel wide-panel offending-panel">
        <div className="trend-table-wrap">
          <TopOffendingFilesTable files={runTopFiles} onFileClick={onFileClick} />
        </div>
      </section>
    </>
  );
}

export default function RunOverviewPanel({ dashboard, selectedRunId, onDimensionClick, onFileClick }) {
  const runSummary = useMemo(() => buildRunSummary(dashboard?.dimensions), [dashboard]);
  const runTopFiles = useMemo(() => withDimensionsStr(buildTopOffendingFiles(dashboard?.dimensions || [])), [dashboard]);
  const dimensionsWithViolations = useMemo(() => sortDimensionsByViolationSeverity(dashboard?.dimensions || []), [dashboard]);
  const runScoreDelta = useMemo(() => computeRunScoreDelta(dashboard), [dashboard]);
  const runUniquePrinciples = useMemo(() => {
    const violations = (dashboard?.dimensions || []).flatMap((d) => d.violations || []);
    return new Set(violations.map((v) => v.principle).filter(Boolean)).size;
  }, [dashboard]);

  if (!dashboard) return <p className="empty-state">Loading run data...</p>;

  return (
    <>
      <RunHeroSection dashboard={dashboard} selectedRunId={selectedRunId} stats={{ runSummary, runScoreDelta, runTopFiles, runUniquePrinciples }} />
      <div className="dimensions-header">
        <h3 className="dimensions-title">Dimensions Analyzed</h3>
      </div>
      <div className="dimensions-panel">
        <RunDimensionsGrid dimensions={dashboard?.dimensions || []} selectedRunId={selectedRunId} dateLabel={dashboard?.selectedRun?.dateLabel} onDimensionClick={onDimensionClick} />
      </div>
      <ViolationsByDimension dimensionsWithViolations={dimensionsWithViolations} onDimensionClick={onDimensionClick} selectedRunId={selectedRunId} />
      <RunFileViolations runTopFiles={runTopFiles} onFileClick={onFileClick} />
    </>
  );
}
