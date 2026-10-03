import { withPending } from '../../../utils/pendingClass.js';
import { useMemo } from 'react';
import LoadingScreen from '../../../components/LoadingScreen.jsx';
import TopOffendingFilesTable from './TopOffendingFilesTable.jsx';
import DimensionGaugeCard from './DimensionGaugeCard.jsx';
import { SectionLabel } from '../../../components/terminal/index.js';

import { buildProjectRootFile } from '../../../utils/explorerUtils.js';
import { formatRunId } from '../../../utils/formatters.js';
import { t } from '../../../strings/index.js';
import { RunHeroSection } from './RunHeroSection.jsx';
import { chipDeltas } from '../headlineStats.js';
import { buildRunViewData } from '../runViewData.js';
import { useRunReportSpecs } from './runReportSpecs.jsx';
import { useRunFindings } from '../hooks/useRunFindings.js';
import { HERO_CARD_KIND } from '../dashboardVocab.js';
import { SEVERITY_FILTER_ALL } from '../../../vocab/severity.js';
import { NAV_TAB } from '../../../vocab/navTab.js';

export { RunHeroSection };

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

function RunFileViolations({ runTopFiles, onFileClick }) {
  if (runTopFiles.length === 0) return null;
  return (
    <section className="qd-cards-panel offending-panel" aria-label={t('overview.violationsByFileAria')}>
      <div className="qd-cards-panel__head">
        <SectionLabel>{t('overview.violationsByFileLabel')} · {runTopFiles.length}</SectionLabel>
        <span className="run-history-panel__stats">{t('overview.sortedBySeverity')}</span>
      </div>
      <TopOffendingFilesTable files={runTopFiles} onFileClick={onFileClick} />
    </section>
  );
}

// Per-dimension deltas from the trend entry (same source the history rows use)
function useTrendDeltas(dashboard) {
  return useMemo(() => {
    const currentRunId = dashboard?.selectedRun?.runId;
    const entry = (dashboard?.trend || []).find((item) => item.runId === currentRunId);
    if (!entry?.dimensionDetails) return {};
    const lookup = {};
    for (const d of entry.dimensionDetails) {
      if (d.delta != null) lookup[(d.dimension || '').toLowerCase()] = d.delta;
    }
    return lookup;
  }, [dashboard]);
}

function useCardNavigate({ dimensions, selectedRunId, projectName, runDateLabel, onNavigate }) {
  return useMemo(() => {
    if (!onNavigate) return undefined;
    return (kind) => {
      const label = `${projectName || 'project'} · ${runDateLabel || 'run'}`;
      const projectFile = buildProjectRootFile(dimensions, label);
      const severityFilter = kind === HERO_CARD_KIND.VIOLATIONS ? SEVERITY_FILTER_ALL : kind;
      onNavigate(NAV_TAB.FILE, { file: projectFile, severityFilter, runId: selectedRunId, dateLabel: runDateLabel });
    };
  }, [onNavigate, dimensions, projectName, runDateLabel, selectedRunId]);
}

// The run's derived view data: summary, worst files, hero-card navigation and
// the per-dimension deltas; also registers this run's report specs. The
// dashboard is the overview shape (scores and counts); the finding lists the
// worst files, navigation, report and fix plan need come from the run's
// scores query and are merged in by dimension.
function useRunOverviewModel({ dashboard, selectedRunId, selectedProject, selectedSource, availableRuns, projectName, onNavigate }) {
  const runId = dashboard?.selectedRun?.runId || selectedRunId;
  const findings = useRunFindings({ project: selectedProject, runId, source: selectedSource, availableRuns, enabled: !!dashboard?.dimensions });
  const { dimensions, runSummary, since, runTopFiles, headline } = useMemo(
    () => buildRunViewData(dashboard, findings.dimensions),
    [dashboard, findings.dimensions],
  );
  const runDateLabel = dashboard?.selectedRun?.dateLabel || formatRunId(selectedRunId);
  const onCardNavigate = useCardNavigate({ dimensions, selectedRunId, projectName, runDateLabel, onNavigate });
  const reportDashboard = useMemo(() => (dashboard ? { ...dashboard, dimensions } : dashboard), [dashboard, dimensions]);
  useRunReportSpecs({ dashboard: reportDashboard, runSummary, selectedRunId, projectName, headline, since });
  const trendDeltas = useTrendDeltas(dashboard);
  return { runSummary, runTopFiles, onCardNavigate, trendDeltas, since, headline };
}

export default function RunOverviewPanel({
  dashboard, selectedRunId, selectedProject, selectedSource, availableRuns, projectName,
  onDimensionClick, onFileClick, onNavigate, refreshing = false,
}) {
  const { runSummary, runTopFiles, onCardNavigate, trendDeltas, since, headline } = useRunOverviewModel({
    dashboard, selectedRunId, selectedProject, selectedSource, availableRuns, projectName, onNavigate,
  });

  const isLoading = !dashboard || !dashboard.dimensions;
  if (isLoading) {
    return (
      <div className="run-overview-fade run-overview-loading">
        <div className="run-overview-spinner"><LoadingScreen variant="inline" /></div>
      </div>
    );
  }
  const dimCount = (dashboard?.dimensions || []).length;

  return (
    <div className={withPending('run-overview-fade run-overview-ready', refreshing)} aria-busy={refreshing || undefined}>
      <RunHeroSection dashboard={dashboard} selectedRunId={selectedRunId} runSummary={runSummary} onCardNavigate={onCardNavigate} deltas={chipDeltas(since)} density={headline.density} />
      <section className="quality-dimensions" aria-label={t('overview.qualityDimensionsAria')}>
        <div className="quality-dimensions__head">
          <SectionLabel>{t('overview.qualityDimensionsLabel')} · {dimCount}</SectionLabel>
        </div>
        <div className="dimensions-panel">
          <RunDimensionsGrid dimensions={dashboard?.dimensions || []} selectedRunId={selectedRunId} dateLabel={dashboard?.selectedRun?.dateLabel} onDimensionClick={onDimensionClick} trendDeltas={trendDeltas} />
        </div>
      </section>
      <RunFileViolations runTopFiles={runTopFiles} onFileClick={onFileClick} />
    </div>
  );
}
