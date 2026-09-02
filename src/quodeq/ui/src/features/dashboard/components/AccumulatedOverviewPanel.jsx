import { useMemo, lazy, Suspense } from 'react';
import DimensionCardsGrid from './DimensionCardsGrid.jsx';
const runHistoryPanelImport = () => import('./RunHistoryPanel.jsx');
const RunHistoryPanel = lazy(runHistoryPanelImport);

// Warm the chart chunk before the overview first mounts with data (called
// from DashboardPage while the boot loader / skeleton is still up). The
// dynamic import caches, so the lazy() above resolves without ever
// committing its RunHistoryPanelPlaceholder fallback — otherwise a cold
// boot pays a placeholder beat inside otherwise-real content.
export function preloadRunHistoryPanel() {
  runHistoryPanelImport();
}
import RunHistoryPanelPlaceholder from './RunHistoryPanelPlaceholder.jsx';
import DimensionScorePanel from './DimensionScorePanel.jsx';
import TopOffendingFilesTable from './TopOffendingFilesTable.jsx';
import { buildTopOffendingFiles, buildProjectRootFile } from '../../../utils/explorerUtils.js';
import { withDimensionsStr } from '../../../utils/dimensionUtils.js';
import { SectionLabel } from '../../../components/terminal/index.js';
import { t } from '../../../strings/index.js';
import { useAccumulatedComputations, computeAccumulatedStats } from '../hooks/useAccumulatedComputations.js';
import { AccumulatedHeroSection } from './AccumulatedHeroSection.jsx';
import { useAccumulatedReportSpec } from './accumulatedReportSpecs.jsx';

export { useAccumulatedComputations, computeAccumulatedStats, AccumulatedHeroSection };

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function AccumulatedDimensionsSection({ sortedDimensions, onDimensionClick, selectedDayDimNames, dimTrends, pending }) {
  return (
    <section
      className={`quality-dimensions${pending ? ' quality-dimensions--pending' : ''}`}
      aria-label={t('overview.qualityDimensionsAria')}
      aria-busy={pending || undefined}
    >
      <div className="quality-dimensions__head">
        <SectionLabel>{t('overview.qualityDimensionsLabel')} · {sortedDimensions.length}</SectionLabel>
        {pending && <span className="quality-dimensions__pending">{t('overview.updating')}</span>}
      </div>
      <div className="dimensions-panel">
        <DimensionCardsGrid
          sortedDimensions={sortedDimensions}
          onDimensionClick={onDimensionClick}
          selectedDayDimNames={selectedDayDimNames}
          dimTrends={dimTrends}
        />
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Accumulated overview panel
// ---------------------------------------------------------------------------

export default function AccumulatedOverviewPanel({ data, callbacks }) {
  const { onRunClick, onDimensionClick, onNavigate } = callbacks;
  const { currentOverviewRun, selectedDayDimNames, filteredPeriodTrend, filteredTrend, filteredDimensions, filteredAccumulated, filteredStats, chartMountable, dimTrends } = useAccumulatedComputations(data);

  const topFiles = useMemo(
    () => withDimensionsStr(buildTopOffendingFiles(filteredDimensions || [])),
    [filteredDimensions]
  );

  const reportProjectName = useAccumulatedReportSpec({ data, filteredAccumulated, filteredDimensions });

  const onCardNavigate = useMemo(() => {
    if (!onNavigate) return undefined;
    return (kind) => {
      const projectFile = buildProjectRootFile(filteredDimensions || [], reportProjectName);
      const severityFilter = kind === 'violations' ? 'all' : kind;
      onNavigate('file', { file: projectFile, severityFilter });
    };
  }, [onNavigate, filteredDimensions, reportProjectName]);

  return (
    <>
      <AccumulatedHeroSection
        accumulated={filteredAccumulated}
        scoreDelta={filteredStats.scoreDelta}
        lastDate={filteredStats.lastRun.date}
        accumulatedDimensions={filteredDimensions}
        projectName={data.selectedProject}
        projectInfo={data.projectInfo}
        onCardNavigate={onCardNavigate}
        selectedSource={data.selectedSource}
        customFormula={data.customFormula}
      />

      <div className="history-panels-row">
        <Suspense fallback={<RunHistoryPanelPlaceholder />}>
          {chartMountable && (
            <RunHistoryPanel
              trend={filteredPeriodTrend}
              selectedRunId={currentOverviewRun}
              onBarClick={onRunClick}
              granularity={data.granularity || 'day'}
              onGranularityChange={callbacks.onGranularityChange}
            />
          )}
        </Suspense>
        <DimensionScorePanel dimensions={filteredDimensions} onBarClick={onDimensionClick} dimTrends={dimTrends} />
      </div>

      <AccumulatedDimensionsSection
        sortedDimensions={filteredStats.sorted}
        onDimensionClick={onDimensionClick}
        selectedDayDimNames={selectedDayDimNames}
        dimTrends={dimTrends}
        pending={data.scoresPending}
      />

      {topFiles.length > 0 && (
        <section className="qd-cards-panel offending-panel" aria-label={t('overview.violationsByFileAria')}>
          <div className="qd-cards-panel__head">
            <SectionLabel>{t('overview.violationsByFileLabel')} · {topFiles.length}</SectionLabel>
            <span className="run-history-panel__stats">{t('overview.sortedBySeverity')}</span>
          </div>
          <TopOffendingFilesTable
            files={topFiles}
            onFileClick={onNavigate ? (f) => onNavigate('file', { file: f }) : undefined}
          />
        </section>
      )}
    </>
  );
}
