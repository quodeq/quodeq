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

function HistoryPanelsRow({
  chartMountable, filteredPeriodTrend, currentOverviewRun, onRunClick, granularity, onGranularityChange,
  filteredDimensions, onDimensionClick, dimTrends,
}) {
  return (
    <div className="history-panels-row">
      <Suspense fallback={<RunHistoryPanelPlaceholder />}>
        {chartMountable && (
          <RunHistoryPanel
            trend={filteredPeriodTrend}
            selectedRunId={currentOverviewRun}
            onBarClick={onRunClick}
            granularity={granularity || 'day'}
            onGranularityChange={onGranularityChange}
          />
        )}
      </Suspense>
      <DimensionScorePanel dimensions={filteredDimensions} onBarClick={onDimensionClick} dimTrends={dimTrends} />
    </div>
  );
}

function OffendingFilesSection({ topFiles, onNavigate }) {
  if (topFiles.length === 0) return null;
  return (
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
  );
}

function makeCardNavigate({ onNavigate, filteredDimensions, reportProjectName }) {
  if (!onNavigate) return undefined;
  return (kind) => {
    const projectFile = buildProjectRootFile(filteredDimensions || [], reportProjectName);
    const severityFilter = kind === 'violations' ? 'all' : kind;
    onNavigate('file', { file: projectFile, severityFilter });
  };
}

function AccumulatedOverviewSections({
  data, callbacks, currentOverviewRun, selectedDayDimNames, filteredPeriodTrend, filteredDimensions,
  filteredAccumulated, filteredStats, chartMountable, dimTrends, topFiles, onCardNavigate,
}) {
  const { onRunClick, onDimensionClick, onNavigate } = callbacks;
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

      <HistoryPanelsRow
        chartMountable={chartMountable}
        filteredPeriodTrend={filteredPeriodTrend}
        currentOverviewRun={currentOverviewRun}
        onRunClick={onRunClick}
        granularity={data.granularity}
        onGranularityChange={callbacks.onGranularityChange}
        filteredDimensions={filteredDimensions}
        onDimensionClick={onDimensionClick}
        dimTrends={dimTrends}
      />

      <AccumulatedDimensionsSection
        sortedDimensions={filteredStats.sorted}
        onDimensionClick={onDimensionClick}
        selectedDayDimNames={selectedDayDimNames}
        dimTrends={dimTrends}
        pending={data.scoresPending}
      />

      <OffendingFilesSection topFiles={topFiles} onNavigate={onNavigate} />
    </>
  );
}

export default function AccumulatedOverviewPanel({ data, callbacks }) {
  const { onNavigate } = callbacks;
  const { currentOverviewRun, selectedDayDimNames, filteredPeriodTrend, filteredTrend, filteredDimensions, filteredAccumulated, filteredStats, chartMountable, dimTrends } = useAccumulatedComputations(data);

  const topFiles = useMemo(
    () => withDimensionsStr(buildTopOffendingFiles(filteredDimensions || [])),
    [filteredDimensions]
  );

  const reportProjectName = useAccumulatedReportSpec({ data, filteredAccumulated, filteredDimensions });

  const onCardNavigate = useMemo(
    () => makeCardNavigate({ onNavigate, filteredDimensions, reportProjectName }),
    [onNavigate, filteredDimensions, reportProjectName],
  );

  return (
    <AccumulatedOverviewSections
      data={data} callbacks={callbacks} currentOverviewRun={currentOverviewRun}
      selectedDayDimNames={selectedDayDimNames} filteredPeriodTrend={filteredPeriodTrend}
      filteredDimensions={filteredDimensions} filteredAccumulated={filteredAccumulated}
      filteredStats={filteredStats} chartMountable={chartMountable} dimTrends={dimTrends}
      topFiles={topFiles} onCardNavigate={onCardNavigate}
    />
  );
}
