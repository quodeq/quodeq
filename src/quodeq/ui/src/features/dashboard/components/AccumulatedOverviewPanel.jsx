import { useMemo, useState, lazy, Suspense } from 'react';
import DimensionCardsGrid from './DimensionCardsGrid.jsx';
import RunHistoryPanelPlaceholder from './RunHistoryPanelPlaceholder.jsx';
import TopOffendingFilesTable from './TopOffendingFilesTable.jsx';
import FindingsByFolderPanel from './FindingsByFolderPanel.jsx';
import FixFirstPanel from './FixFirstPanel.jsx';
import ListShowMore from './ListShowMore.jsx';
import { buildTopOffendingFiles, buildProjectRootFile } from '../../../utils/explorerUtils.js';
import { withDimensionsStr } from '../../../utils/dimensionUtils.js';
import { SectionLabel } from '../../../components/terminal/index.js';
import { t, LOCALE } from '../../../strings/index.js';
import { DEFAULT_SCORE_HISTORY_GRANULARITY } from '../../../constants.js';
import { HERO_CARD_KIND } from '../dashboardVocab.js';
import { buildHeadline, filterSinceBaseline, periodChipDeltas, sumSinceBaseline } from '../headlineStats.js';
import { SEVERITY_FILTER_ALL } from '../../../vocab/severity.js';
import { useAccumulatedComputations, computeAccumulatedStats } from '../hooks/useAccumulatedComputations.js';
import { AccumulatedHeroSection } from './AccumulatedHeroSection.jsx';
import { useAccumulatedReportSpec } from './accumulatedReportSpecs.jsx';
import { NAV_TAB } from '../../../vocab/navTab.js';
import { withPending } from '../../../utils/pendingClass.js';
import { typeFile } from '../../violations/byTypeModel.js';
import { FILE_SELECTOR_KIND } from '../../../routes/liveSelectors.js';
import { folderDimensions } from '../findingsGrouping.js';

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

function AccumulatedDimensionsSection({ sortedDimensions, onDimensionClick, selectedDayDimNames, dimTrends, pending, notEvaluated, onEvaluate }) {
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
          notEvaluated={notEvaluated}
          onEvaluate={onEvaluate}
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
  filteredDimensions, onFolderClick, pending,
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
      <FindingsByFolderPanel dimensions={filteredDimensions} onFolderClick={onFolderClick} />
    </div>
  );
}

// The files table opens on the most severe few; the rest are one click away.
const FILES_SHOWN = 8;

function OffendingFilesSection({ topFiles, onNavigate, pending }) {
  const [open, setOpen] = useState(false);
  if (topFiles.length === 0) return null;
  return (
    <section className={withPending('qd-cards-panel offending-panel', pending)} aria-label={t('overview.violationsByFileAria')} aria-busy={pending || undefined}>
      <div className="qd-cards-panel__head">
        <SectionLabel>{t('overview.violationsByFileLabel')} · {topFiles.length}</SectionLabel>
        <span className="run-history-panel__stats">{t('overview.sortedBySeverity')}</span>
      </div>
      <TopOffendingFilesTable
        files={open ? topFiles : topFiles.slice(0, FILES_SHOWN)}
        onFileClick={onNavigate ? (f) => onNavigate(NAV_TAB.FILE, { file: f }) : undefined}
      />
      <ListShowMore
        open={open} total={topFiles.length} shown={FILES_SHOWN}
        allLabel={t('overview.showAllFiles', { count: topFiles.length.toLocaleString(LOCALE) })}
        onToggle={() => setOpen(!open)}
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

/** Fix first: a requirement opens on its findings, live like the By type view's. */
function makeRequirementNavigate({ onNavigate, filteredDimensions }) {
  if (!onNavigate) return undefined;
  return (row) => {
    const dim = (filteredDimensions || []).find((d) => d.dimension === row.dimension);
    if (!dim) return;
    const violations = (dim.violations || []).filter((v) => v.req === row.req);
    onNavigate(NAV_TAB.FILE, {
      file: typeFile({ violations }, dim, `${row.req} · ${row.text}`),
      fileSelector: { kind: FILE_SELECTOR_KIND.TYPE, dimension: row.dimension, req: row.req, text: row.text },
      severityFilter: SEVERITY_FILTER_ALL,
      runId: dim.fromRunId,
      dateLabel: dim.fromDateLabel,
    });
  };
}

/** Where the findings live: a folder opens on its findings across the dimensions on show. */
function makeFolderNavigate({ onNavigate, filteredDimensions }) {
  if (!onNavigate) return undefined;
  return (row) => {
    const label = `${row.dir}/`;
    onNavigate(NAV_TAB.FILE, {
      file: buildProjectRootFile(folderDimensions(filteredDimensions, row.dir), label),
      fileSelector: { kind: FILE_SELECTOR_KIND.FOLDER, dir: row.dir, dimensions: (filteredDimensions || []).map((d) => d.dimension), label },
      severityFilter: SEVERITY_FILTER_ALL,
    });
  };
}

function AccumulatedOverviewSections({
  data, callbacks, currentOverviewRun, selectedDayDimNames, filteredPeriodTrend, filteredDimensions,
  filteredAccumulated, filteredStats, chartMountable, dimTrends, topFiles, onCardNavigate, headline, notEvaluated,
}) {
  const { onRunClick, onRunHover, onRunHoverEnd, onDimensionClick, onNavigate } = callbacks;
  const onFolderClick = useMemo(() => makeFolderNavigate({ onNavigate, filteredDimensions }), [onNavigate, filteredDimensions]);
  const onRequirementClick = useMemo(() => makeRequirementNavigate({ onNavigate, filteredDimensions }), [onNavigate, filteredDimensions]);
  const onEvaluate = onNavigate ? () => onNavigate(NAV_TAB.EVALUATE) : undefined;
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
        onFolderClick={onFolderClick}
      />

      <AccumulatedDimensionsSection
        sortedDimensions={filteredStats.sorted}
        onDimensionClick={onDimensionClick}
        selectedDayDimNames={selectedDayDimNames}
        dimTrends={dimTrends}
        pending={pending}
        notEvaluated={notEvaluated}
        onEvaluate={onEvaluate}
      />

      <FixFirstPanel dimensions={filteredDimensions} onRequirementClick={onRequirementClick} />

      <OffendingFilesSection topFiles={topFiles} onNavigate={onNavigate} pending={pending} />
    </>
  );
}

export default function AccumulatedOverviewPanel({ data, callbacks }) {
  const { onNavigate } = callbacks;
  const { currentOverviewRun, selectedDayDimNames, filteredPeriodTrend, filteredDimensions, filteredAccumulated, filteredStats, chartMountable, dimTrends, visibleSet } = useAccumulatedComputations(data);
  // Standards switched on but never evaluated: shown as empty cards.
  const notEvaluated = useMemo(() => {
    const evaluated = new Set((data.accumulatedDimensions || []).map((d) => (d.dimension || '').toLowerCase()));
    return [...(visibleSet || [])].filter((id) => !evaluated.has(id));
  }, [visibleSet, data.accumulatedDimensions]);

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
      notEvaluated={notEvaluated}
    />
  );
}
