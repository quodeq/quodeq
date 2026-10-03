import { useMemo, lazy, Suspense } from 'react';
import DimensionCardsGrid from './DimensionCardsGrid.jsx';
import RunHistoryPanelPlaceholder from './RunHistoryPanelPlaceholder.jsx';
import DimensionScorePanel from './DimensionScorePanel.jsx';
import TopOffendingFilesTable from './TopOffendingFilesTable.jsx';
import { buildTopOffendingFiles, buildProjectRootFile } from '../../../utils/explorerUtils.js';
import { withDimensionsStr } from '../../../utils/dimensionUtils.js';
import { SectionLabel } from '../../../components/terminal/index.js';
import { t } from '../../../strings/index.js';
import { DEFAULT_SCORE_HISTORY_GRANULARITY } from '../../../constants.js';
import { HERO_CARD_KIND } from '../dashboardVocab.js';
import { buildHeadline, filterSinceBaseline, periodChipDeltas, sumSinceBaseline } from '../headlineStats.js';
import { SEVERITY_FILTER_ALL } from '../../../vocab/severity.js';
import { useAccumulatedComputations, computeAccumulatedStats } from '../hooks/useAccumulatedComputations.js';
import { AccumulatedHeroSection } from './AccumulatedHeroSection.jsx';
import { useAccumulatedReportSpec } from './accumulatedReportSpecs.jsx';
import { NAV_TAB } from '../../../vocab/navTab.js';
import { withPending } from '../../../utils/pendingClass.js';

const runHistoryPanelImport = () => import('./RunHistoryPanel.jsx');
const RunHistoryPanel = lazy(runHistoryPanelImport);

// Warm the chart chunk before the overview first mounts with data (called
// from DashboardPage while the boot loader / skeleton is still up). The
// dynamic import caches, so the lazy() above resolves without ever
// committing its RunHistoryPanelPlaceholder fallback -- otherwise a cold
// boot pays a placeholder beat inside otherwise-real content.
export function preloadRunHistoryPanel() {
  runHistoryPanelImport().catch((err) => {
    console.warn('[AccumulatedOverviewPanel] chart chunk preload failed:', err);
  });
}

export { useAccumulatedComputations, computeAccumulatedStats, AccumulatedHeroSection };

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function AccumulatedDimensionsSection({ sortedDimensions, onDimensionClick, selectedDayDimNames, dimTrends, pending }) {
  return (
    <section
      className={withPending('quality-dimensions', pending)}
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
  chartMountable, filteredPeriodTrend, currentOverviewRun, onRunClick, onRunHover, onRunHoverEnd, granularity, onGranularityChange,
  filteredDimensions, onDimensionClick, dimTrends, pending,
}) {
  return (
    <div className={withPending('history-panels-row', pending)} aria-busy={pending || undefined}>
      <Suspense fallback={<RunHistoryPanelPlaceholder />}>
        {chartMountable && (
          <RunHistoryPanel
            trend={filteredPeriodTrend}
            selectedRunId={currentOverviewRun}
            onBarClick={onRunClick}
            onBarHover={onRunHover}
            onBarHoverEnd={onRunHoverEnd}
            granularity={granularity || DEFAULT_SCORE_HISTORY_GRANULARITY}
            onGranularityChange={onGranularityChange}
          />
        )}
      </Suspense>
      <DimensionScorePanel dimensions={filteredDimensions} onBarClick={onDimensionClick} dimTrends={dimTrends} />
    </div>
  );
}

function OffendingFilesSection({ topFiles, onNavigate, pending }) {
  if (topFiles.length === 0) return null;
  return (
    <section className={withPending('qd-cards-panel offending-panel', pending)} aria-label={t('overview.violationsByFileAria')} aria-busy={pending || undefined}>
      <div className="qd-cards-panel__head">
        <SectionLabel>{t('overview.violationsByFileLabel')} · {topFiles.length}</SectionLabel>
        <span className="run-history-panel__stats">{t('overview.sortedBySeverity')}</span>
      </div>
      <TopOffendingFilesTable
        files={topFiles}
        onFileClick={onNavigate ? (f) => onNavigate(NAV_TAB.FILE, { file: f }) : undefined}
      />
    </section>
  );
}

function makeCardNavigate({ onNavigate, filteredDimensions, reportProjectName }) {
  if (!onNavigate) return undefined;
  return (kind) => {
    const projectFile = buildProjectRootFile(filteredDimensions || [], reportProjectName);
    const severityFilter = kind === HERO_CARD_KIND.VIOLATIONS ? SEVERITY_FILTER_ALL : kind;
    onNavigate(NAV_TAB.FILE, { file: projectFile, severityFilter });
  };
}

function AccumulatedOverviewSections({
  data, callbacks, currentOverviewRun, selectedDayDimNames, filteredPeriodTrend, filteredDimensions,
  filteredAccumulated, filteredStats, chartMountable, dimTrends, topFiles, onCardNavigate, headline,
}) {
  const { onRunClick, onRunHover, onRunHoverEnd, onDimensionClick, onNavigate } = callbacks;
  // A run or date switch refetches the dashboard and the scores; every
  // section shows the previous values, muted, meanwhile.
  const pending = !!(data.scoresPending || data.refreshing);
  return (
    <>
      <AccumulatedHeroSection
        pending={pending}
        accumulated={filteredAccumulated}
        scoreDelta={filteredStats.scoreDelta}
        lastDate={filteredStats.lastRun.date}
        projectInfo={data.projectInfo}
        onCardNavigate={onCardNavigate}
        selectedSource={data.selectedSource}
        customFormula={data.customFormula}
        deltas={periodChipDeltas(filteredPeriodTrend, currentOverviewRun)}
        density={headline.density}
      />
      <HistoryPanelsRow
        chartMountable={chartMountable}
        filteredPeriodTrend={filteredPeriodTrend}
        currentOverviewRun={currentOverviewRun}
        onRunClick={onRunClick}
        onRunHover={onRunHover}
        onRunHoverEnd={onRunHoverEnd}
        pending={pending}
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
        pending={pending}
      />

      <OffendingFilesSection topFiles={topFiles} onNavigate={onNavigate} pending={pending} />
    </>
  );
}

export default function AccumulatedOverviewPanel({ data, callbacks }) {
  const { onNavigate } = callbacks;
  const { currentOverviewRun, selectedDayDimNames, filteredPeriodTrend, filteredDimensions, filteredAccumulated, filteredStats, chartMountable, dimTrends } = useAccumulatedComputations(data);

  const topFiles = useMemo(
    () => withDimensionsStr(buildTopOffendingFiles(filteredDimensions || [])),
    [filteredDimensions]
  );

  // Only the dimensions on show: a hidden standard must not move the report.
  // (The hero chips take their deltas from the period trend instead, so they
  // follow the chart's grouping like the score arrow; see periodChipDeltas.)
  const since = useMemo(
    () => sumSinceBaseline(filterSinceBaseline(data.sinceBaseline, (filteredDimensions || []).map((d) => d.dimension))),
    [data.sinceBaseline, filteredDimensions],
  );
  const headline = useMemo(() => buildHeadline(filteredAccumulated?.dimensions), [filteredAccumulated]);
  const reportProjectName = useAccumulatedReportSpec({ data, filteredAccumulated, filteredDimensions, headline, since });

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
      topFiles={topFiles} onCardNavigate={onCardNavigate} headline={headline}
    />
  );
}
