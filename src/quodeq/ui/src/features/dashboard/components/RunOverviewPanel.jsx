import { useMemo } from 'react';
import LoadingScreen from '../../../components/LoadingScreen.jsx';
import TopOffendingFilesTable from './TopOffendingFilesTable.jsx';
import DimensionGaugeCard from './DimensionGaugeCard.jsx';
import { SectionLabel } from '../../../components/terminal/index.js';

import { buildTopOffendingFiles, buildProjectRootFile } from '../../../utils/explorerUtils.js';
import { formatRunId } from '../../../utils/formatters.js';
import { withDimensionsStr } from '../../../utils/dimensionUtils.js';
import buildRunSummary from '../buildRunSummary.js';
import { t } from '../../../strings/index.js';
import { RunHeroSection } from './RunHeroSection.jsx';
import { useRunReportSpecs } from './runReportSpecs.jsx';

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
    const entry = (dashboard?.trend || []).find((t) => t.runId === currentRunId);
    if (!entry?.dimensionDetails) return {};
    const lookup = {};
    for (const d of entry.dimensionDetails) {
      if (d.delta != null) lookup[(d.dimension || '').toLowerCase()] = d.delta;
    }
    return lookup;
  }, [dashboard]);
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

  useRunReportSpecs({ dashboard, runSummary, selectedRunId, projectName });
  const trendDeltas = useTrendDeltas(dashboard);

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
    <div className="run-overview-fade run-overview-ready">
      <RunHeroSection dashboard={dashboard} selectedRunId={selectedRunId} runSummary={runSummary} onCardNavigate={onCardNavigate} />
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
