import { useMemo } from 'react';
import LoadingScreen from '../../../components/LoadingScreen.jsx';
import TopOffendingFilesTable from './TopOffendingFilesTable.jsx';
import CopyButton, { SparkleIcon } from '../../../components/CopyButton.jsx';
import ScoreCircle from '../../../components/ScoreCircle.jsx';
import DimensionGaugeCard from './DimensionGaugeCard.jsx';
import { SectionLabel } from '../../../components/terminal/index.js';

const HERO_SCORE_CIRCLE_SIZE = 120;
import { copyToClipboard } from '../../../utils/clipboard.js';
import { buildTopOffendingFiles, buildDimensionPlanFromViolations } from '../../../utils/explorerUtils.js';
import { buildRunReport } from '../../../utils/reportBuilder.js';
import { formatRunId, complianceRatio } from '../../../utils/formatters.js';
import { withDimensionsStr } from '../../../utils/dimensionUtils.js';
import { useRegisterWindowSpec, ReportContent } from '../../side-pane/index.js';
import buildRunSummary from '../buildRunSummary.js';

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function RunDimensionsGrid({ dimensions, selectedRunId, dateLabel, onDimensionClick, trendDeltas }) {
  const sorted = useMemo(
    () => [...dimensions].sort((a, b) => a.dimension.localeCompare(b.dimension)),
    [dimensions]
  );
  return (
    <div className="dimensions-grid">
      {sorted.map((item) => (
        <DimensionGaugeCard
          key={item.dimension}
          item={item}
          delta={trendDeltas?.[(item.dimension || '').toLowerCase()] ?? null}
          onDimensionClick={onDimensionClick}
          selectedRunId={selectedRunId}
          dateLabel={dateLabel}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Run-specific overview panel
// ---------------------------------------------------------------------------

function StatsGrid({ runSummary, runTopFiles, runUniquePrinciples }) {
  return (
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
        <span className="acc-eval-stat-value">{complianceRatio(runSummary.totalViolations || 0, runSummary.totalCompliance || 0)}</span>
      </div>
      <div className="acc-eval-stats-divider" />
      <div className="acc-eval-stat-block">
        <span className="acc-eval-stat-label">Files</span>
        <span className="acc-eval-stat-value">{runTopFiles.length}</span>
      </div>
      <div className="acc-eval-stats-divider" />
      <div className="acc-eval-stat-block">
        <span className="acc-eval-stat-label">Principles</span>
        <span className="acc-eval-stat-value">{runUniquePrinciples}</span>
      </div>
      <div className="acc-eval-stats-divider" />
      <div className="acc-eval-stat-block">
        <span className="acc-eval-stat-label">Dimensions</span>
        <span className="acc-eval-stat-value">{runSummary.dimensionCount || 0}</span>
      </div>
    </div>
  );
}

function RunHeroSection({ dashboard, selectedRunId, stats }) {
  const { runSummary, runTopFiles, runUniquePrinciples } = stats;
  return (
    <section className="acc-eval-panel panel">
      <div className="acc-eval-top">
        <span className="acc-eval-date">{dashboard?.selectedRun?.dateLabel || formatRunId(selectedRunId)}</span>
        {(dashboard?.dimensions || []).some((d) => (d.violations?.length || 0) > 0) && (
          <CopyButton
            label="Full fix plan"
            className="fix-plan-btn-header"
            icon={<SparkleIcon />}
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
          <ScoreCircle score={runSummary.numericAverage} grade={runSummary.overallGrade} size={HERO_SCORE_CIRCLE_SIZE} />
        </div>
        <div className="acc-eval-stats-col">
          <StatsGrid runSummary={runSummary} runTopFiles={runTopFiles} runUniquePrinciples={runUniquePrinciples} />
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

export default function RunOverviewPanel({ dashboard, selectedRunId, projectName, onDimensionClick, onFileClick }) {
  const runSummary = useMemo(() => buildRunSummary(dashboard?.dimensions), [dashboard]);
  const runTopFiles = useMemo(() => withDimensionsStr(buildTopOffendingFiles(dashboard?.dimensions || [])), [dashboard]);
  const runUniquePrinciples = useMemo(() => {
    const violations = (dashboard?.dimensions || []).flatMap((d) => d.violations || []);
    return new Set(violations.map((v) => v.principle).filter(Boolean)).size;
  }, [dashboard]);

  const reportSpec = useMemo(() => {
    if (!dashboard?.dimensions) return null;
    const runId = dashboard?.selectedRun?.runId || selectedRunId || 'current';
    const dateLabel = dashboard?.selectedRun?.dateLabel || formatRunId(selectedRunId) || 'run';
    const buildMarkdown = () => buildRunReport({ dashboard, runSummary, projectName });
    const filenameLabel = (dateLabel || runId).replace(/[^a-z0-9-]+/gi, '-').toLowerCase();
    return {
      id: `report:run:${runId}`,
      type: 'report',
      title: `${dateLabel} report`,
      render: () => <ReportContent markdown={buildMarkdown()} />,
      copy: () => buildMarkdown(),
      download: () => ({ filename: `run-${filenameLabel}-report.md`, body: buildMarkdown() }),
    };
  }, [dashboard, runSummary, selectedRunId, projectName]);
  useRegisterWindowSpec('report', reportSpec);

  // Per-dimension deltas from the trend entry (same source the history rows use)
  const trendDeltas = useMemo(() => {
    const currentRunId = dashboard?.selectedRun?.runId;
    const entry = (dashboard?.trend || []).find((t) => t.runId === currentRunId);
    if (!entry?.dimensionDetails) return {};
    const lookup = {};
    for (const d of entry.dimensionDetails) {
      if (d.delta != null) lookup[(d.dimension || '').toLowerCase()] = d.delta;
    }
    return lookup;
  }, [dashboard]);

  const isLoading = !dashboard || !dashboard.dimensions;
  const dimCount = (dashboard?.dimensions || []).length;

  return (
    <div className={`run-overview-fade ${isLoading ? 'run-overview-loading' : 'run-overview-ready'}`}>
      {isLoading ? (
        <div className="run-overview-spinner"><LoadingScreen /></div>
      ) : (
        <>
          <RunHeroSection dashboard={dashboard} selectedRunId={selectedRunId} stats={{ runSummary, runTopFiles, runUniquePrinciples }} />
          <section className="quality-dimensions" aria-label="Quality dimensions">
            <div className="quality-dimensions__head">
              <SectionLabel>quality_dimensions · {dimCount}</SectionLabel>
            </div>
            <div className="dimensions-panel">
              <RunDimensionsGrid dimensions={dashboard?.dimensions || []} selectedRunId={selectedRunId} dateLabel={dashboard?.selectedRun?.dateLabel} onDimensionClick={onDimensionClick} trendDeltas={trendDeltas} />
            </div>
          </section>
          <RunFileViolations runTopFiles={runTopFiles} onFileClick={onFileClick} />
        </>
      )}
    </div>
  );
}
