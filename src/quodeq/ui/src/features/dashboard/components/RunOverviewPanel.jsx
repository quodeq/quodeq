import { useMemo } from 'react';
import LoadingScreen from '../../../components/LoadingScreen.jsx';
import TopOffendingFilesTable from './TopOffendingFilesTable.jsx';
import DimensionGaugeCard from './DimensionGaugeCard.jsx';
import { TermHeader, StatStrip, Stat, SevBadge, SectionLabel } from '../../../components/terminal/index.js';

import { buildTopOffendingFiles, buildDimensionPlanFromViolations, buildProjectRootFile } from '../../../utils/explorerUtils.js';
import { buildRunReport } from '../../../utils/reportBuilder.js';
import { formatRunId, gradeLetter, complianceRatio } from '../../../utils/formatters.js';
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

function SeverityBadgeRow({ severity, onSeverityClick }) {
  const sev = severity || {};
  if (!(sev.critical || sev.major || sev.minor)) return null;
  const onClickFor = (level) => onSeverityClick ? () => onSeverityClick(level) : undefined;
  return (
    <span className="acc-eval-sev-row">
      {sev.critical > 0 && <SevBadge level="critical" count={sev.critical} format="count-abbr" onClick={onClickFor('critical')} />}
      {sev.major > 0    && <SevBadge level="major"    count={sev.major}    format="count-abbr" onClick={onClickFor('major')} />}
      {sev.minor > 0    && <SevBadge level="minor"    count={sev.minor}    format="count-abbr" onClick={onClickFor('minor')} />}
    </span>
  );
}

function RunHeroSection({ dashboard, selectedRunId, runSummary, onCardNavigate }) {
  const dateLabel = dashboard?.selectedRun?.dateLabel || formatRunId(selectedRunId);
  const scoreNum = parseFloat(runSummary.numericAverage);
  const scoreDisplay = isNaN(scoreNum) ? '—' : scoreNum.toFixed(1);
  const grade = runSummary.overallGrade;
  const violations = runSummary.totalViolations || 0;
  const compliance = runSummary.totalCompliance || 0;
  const totalChecks = violations + compliance;
  const ratio = complianceRatio(violations, compliance);

  const handleViolations = onCardNavigate && violations > 0 ? () => onCardNavigate('violations') : undefined;
  const handleCompliance = onCardNavigate && compliance > 0 ? () => onCardNavigate('compliance') : undefined;
  const handleSeverity = onCardNavigate ? (level) => onCardNavigate(level) : undefined;

  return (
    <section className="acc-eval-panel acc-eval-panel--terminal">
      <div className="acc-eval-panel__top">
        <TermHeader name="run" sub={dateLabel} />
      </div>
      <StatStrip cards>
        <Stat
          label="SCORE"
          value={scoreDisplay}
          hint={grade ? `grade ${gradeLetter(grade)}` : null}
        />
        <Stat
          label="VIOLATIONS"
          value={violations}
          hint={<SeverityBadgeRow severity={runSummary.severity} onSeverityClick={handleSeverity} />}
          onClick={handleViolations}
          ariaLabel={violations > 0 ? 'Show all violations for this run' : undefined}
        />
        <Stat
          label="COMPLIANCE"
          value={compliance}
          hint={totalChecks > 0 ? `passing / ${totalChecks} checks` : null}
          onClick={handleCompliance}
          ariaLabel={compliance > 0 ? 'Show compliance entries for this run' : undefined}
        />
        <Stat
          label="RATIO"
          value={ratio}
          hint="compliance : violations"
        />
      </StatStrip>
    </section>
  );
}

function RunFileViolations({ runTopFiles, onFileClick }) {
  if (runTopFiles.length === 0) return null;
  return (
    <section className="qd-cards-panel offending-panel" aria-label="Violations by file">
      <div className="qd-cards-panel__head">
        <SectionLabel>{`violations_by_file · ${runTopFiles.length}`}</SectionLabel>
        <span className="run-history-panel__stats">SORTED BY SEVERITY</span>
      </div>
      <TopOffendingFilesTable files={runTopFiles} onFileClick={onFileClick} />
    </section>
  );
}

export default function RunOverviewPanel({ dashboard, selectedRunId, projectName, onDimensionClick, onFileClick, onNavigate }) {
  const runSummary = useMemo(() => buildRunSummary(dashboard?.dimensions), [dashboard]);
  const runTopFiles = useMemo(() => withDimensionsStr(buildTopOffendingFiles(dashboard?.dimensions || [])), [dashboard]);
  const runDateLabel = dashboard?.selectedRun?.dateLabel || formatRunId(selectedRunId);

  const onCardNavigate = useMemo(() => {
    if (!onNavigate) return undefined;
    return (kind) => {
      const label = `${projectName || 'project'} · ${runDateLabel || 'run'}`;
      const projectFile = buildProjectRootFile(dashboard?.dimensions || [], label);
      const severityFilter = kind === 'violations' ? 'all' : kind;
      onNavigate('file', { file: projectFile, severityFilter, runId: selectedRunId, dateLabel: runDateLabel });
    };
  }, [onNavigate, dashboard, projectName, runDateLabel, selectedRunId]);

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

  const fixPlanSpec = useMemo(() => {
    const dims = dashboard?.dimensions || [];
    const hasViolations = dims.some((d) => (d.violations?.length || 0) > 0);
    if (!hasViolations) return null;
    const runId = dashboard?.selectedRun?.runId || selectedRunId || 'current';
    const dateLabel = dashboard?.selectedRun?.dateLabel || formatRunId(selectedRunId) || 'run';
    const filenameLabel = (dateLabel || runId).replace(/[^a-z0-9-]+/gi, '-').toLowerCase();
    const buildMarkdown = () => {
      const allViolations = dims.flatMap((d) => (d.violations || []).map((v) => ({ ...v, dimension: d.dimension })));
      return buildDimensionPlanFromViolations(dateLabel, allViolations);
    };
    return {
      id: `fixplan:run:${runId}`,
      type: 'fixplan',
      title: `${dateLabel} fix plan`,
      render: () => <ReportContent markdown={buildMarkdown()} />,
      copy: () => buildMarkdown(),
      download: () => ({ filename: `run-${filenameLabel}-fix-plan.md`, body: buildMarkdown() }),
    };
  }, [dashboard, selectedRunId]);
  useRegisterWindowSpec('fixplan', fixPlanSpec);

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
          <RunHeroSection dashboard={dashboard} selectedRunId={selectedRunId} runSummary={runSummary} onCardNavigate={onCardNavigate} />
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
