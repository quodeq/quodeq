import React, { useMemo, lazy, Suspense } from 'react';
import TrendBadge from '../../../components/TrendBadge.jsx';
import DimensionCardsGrid from './DimensionCardsGrid.jsx';
import { formatRunId, gradeLetter, complianceRatio, extDisplayName } from '../../../utils/formatters.js';
import { collapseByPeriod, collectPeriodDimensions, bucketKey, extractDimensionPeriodSeries, sliceTrendAtRun } from '../../../utils/dailyGrouping.js';
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
import { TermHeader, StatStrip, Stat, SevBadge, SectionLabel } from '../../../components/terminal/index.js';
import LastFetchedLine from '../../../components/LastFetchedLine.jsx';

import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';
import { filterTrendByVisibleStandards, filterTrendByVisibleStandardsDaily, filterAccumulatedByVisibleStandards } from '../../../utils/scoreFiltering.js';
import { useRegisterWindowSpec, ReportContent } from '../../side-pane/index.js';
import { buildOverviewReport } from '../../../utils/reportBuilder.js';
import SharedReadOnlyBadge from '../../../components/SharedReadOnlyBadge.jsx';
import { t } from '../../../strings/index.js';

// Sparkline history length for the per-dimension period series (matches the
// old DimensionScorePanel SPARKLINE_LIMIT).
const DIM_SPARKLINE_LIMIT = 10;

// ---------------------------------------------------------------------------
// Accumulated overview panel helpers
// ---------------------------------------------------------------------------

// The "vs previous" delta compares two accumulated numericAverage points from the
// trend (this run vs the prior run). With fewer than two trend entries there is no
// comparable previous point, so the delta stays null rather than falling back to
// summary.previousNumericAverage: that value is the prior run's own-dimension average,
// not comparable to the accumulated numericAverage (an apples-to-oranges subtraction).
export function computeAccumulatedStats(accumulatedDimensions, dailyTrend, selectedRunId) {
  let scoreDelta = null;
  if (dailyTrend && dailyTrend.length >= 2) {
    const selectedIdx = selectedRunId ? dailyTrend.findIndex((t) => t.runId === selectedRunId) : 0;
    const idx = selectedIdx >= 0 ? selectedIdx : 0;
    const current = parseFloat(dailyTrend[idx]?.numericAverage);
    const previous = idx + 1 < dailyTrend.length ? parseFloat(dailyTrend[idx + 1]?.numericAverage) : NaN;
    if (!Number.isNaN(current) && !Number.isNaN(previous)) scoreDelta = (current - previous).toFixed(1);
  }

  const withDates = accumulatedDimensions
    .filter((d) => d.fromRunId)
    .map((d) => ({ runId: d.fromRunId, dateISO: d.fromDateIso, dateLabel: d.fromDateLabel }));
  withDates.sort((a, b) => (b.dateISO || '').localeCompare(a.dateISO || ''));
  const lastRun = withDates.length === 0
    ? { date: null, runId: null }
    : { date: withDates[0].dateLabel || formatRunId(withDates[0].runId), runId: withDates[0].runId };

  const sorted = [...accumulatedDimensions].sort((a, b) => a.dimension.localeCompare(b.dimension));

  return { scoreDelta, lastRun, sorted };
}

// ---------------------------------------------------------------------------
// Sub-components
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

const MAX_LANGS_IN_SUB = 5;

function buildLanguageSub(projectInfo) {
  const stats = projectInfo?.languageStats;
  if (!stats) return null;
  const sorted = Object.entries(stats).sort(([, a], [, b]) => b - a).slice(0, MAX_LANGS_IN_SUB);
  if (sorted.length === 0) return null;
  return sorted
    .map(([lang, count]) => `${count} ${extDisplayName(lang).toLowerCase()}`)
    .join('  ');
}

export function AccumulatedHeroSection({ accumulated, scoreDelta, lastDate, accumulatedDimensions, projectName, projectInfo, onCardNavigate, selectedSource, customFormula = false }) {
  const summary = accumulated?.summary;
  const scoreNum = parseFloat(summary?.numericAverage);
  const scoreDisplay = isNaN(scoreNum) ? '—' : scoreNum.toFixed(1);
  const grade = summary?.overallGrade;
  const violations = summary?.totalViolations || 0;
  const compliance = summary?.totalCompliance || 0;
  const totalChecks = violations + compliance;
  const ratio = complianceRatio(violations, compliance);

  const handleViolations = onCardNavigate ? () => onCardNavigate('violations') : undefined;
  const handleCompliance = onCardNavigate && compliance > 0 ? () => onCardNavigate('compliance') : undefined;
  const handleSeverity = onCardNavigate ? (level) => onCardNavigate(level) : undefined;

  return (
    <section className="acc-eval-panel acc-eval-panel--terminal">
      <div className="acc-eval-panel__top">
        <TermHeader
          name={t('overview.termName')}
          sub={buildLanguageSub(projectInfo) || (lastDate ? t('overview.lastEvaluated', { date: lastDate }) : null)}
          badge={selectedSource === 'shared' ? <SharedReadOnlyBadge publishedBy={projectInfo?.publishedBy} /> : null}
        />
        <LastFetchedLine lastFetchedAt={projectInfo?.lastFetchedAt} />
      </div>
      <StatStrip cards>
        <Stat
          label={t('overview.statScore')}
          value={scoreDisplay}
          trailing={scoreDelta !== null ? <TrendBadge delta={scoreDelta} showLabel={false} /> : null}
          // A tuned formula shifts every score at once with no other trace, so
          // say so where the grade is read rather than only on the settings
          // page that changed it.
          hint={grade
            ? t(customFormula ? 'overview.gradeHintCustomFormula' : 'overview.gradeHint',
                { letter: gradeLetter(grade) })
            : null}
        />
        <Stat
          label={t('overview.statViolations')}
          value={violations}
          hint={<SeverityBadgeRow severity={summary?.severity} onSeverityClick={handleSeverity} />}
          onClick={violations > 0 ? handleViolations : undefined}
          ariaLabel={violations > 0 ? t('overview.showAllViolationsAria') : undefined}
        />
        <Stat
          label={t('overview.statCompliance')}
          value={compliance}
          hint={totalChecks > 0 ? t('overview.passingChecks', { count: totalChecks }) : null}
          onClick={handleCompliance}
          ariaLabel={compliance > 0 ? t('overview.showComplianceAria') : undefined}
        />
        <Stat
          label={t('overview.statRatio')}
          value={ratio}
          hint={t('overview.ratioHint')}
        />
      </StatStrip>
    </section>
  );
}

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

export function useAccumulatedComputations(data) {
  const { accumulated, accumulatedDimensions, availableRuns, dailyRuns, overviewRunIndex, trend, selectedRunId, granularity = 'day' } = data;
  const dayRuns = dailyRuns || availableRuns;
  const dayTrend = useMemo(() => collapseByPeriod(trend, 'day'), [trend]);
  const periodTrend = useMemo(() => collapseByPeriod(trend, granularity), [trend, granularity]);

  const effectiveSelectedId = useMemo(() => {
    if (!selectedRunId || !trend.length) return periodTrend[0]?.runId || null;
    const direct = periodTrend.find((t) => t.runId === selectedRunId);
    if (direct) return direct.runId;
    const rawEntry = trend.find((t) => t.runId === selectedRunId);
    if (rawEntry) {
      const key = bucketKey(rawEntry.dateISO, granularity);
      const bucketEntry = periodTrend.find((t) => bucketKey(t.dateISO, granularity) === key);
      if (bucketEntry) return bucketEntry.runId;
    }
    return periodTrend[0]?.runId || null;
  }, [selectedRunId, trend, periodTrend, granularity]);

  const currentOverviewRun = effectiveSelectedId || dayRuns[overviewRunIndex]?.runId || 'latest';
  const selectedDayDimNames = useMemo(
    () => collectPeriodDimensions(trend, currentOverviewRun, granularity) || collectPeriodDimensions(trend, selectedRunId, granularity),
    [trend, currentOverviewRun, selectedRunId, granularity]
  );

  const visibleIds = useMemo(() => readVisibleStandardIds(), [accumulatedDimensions]);
  const visibleSet = useMemo(() => new Set(visibleIds), [visibleIds]);
  const filteredDayTrend = useMemo(() => filterTrendByVisibleStandardsDaily(trend, dayTrend, visibleSet, 'day'), [trend, dayTrend, visibleSet]);
  const filteredPeriodTrend = useMemo(() => filterTrendByVisibleStandardsDaily(trend, periodTrend, visibleSet, granularity), [trend, periodTrend, visibleSet, granularity]);
  // Raw (per-run) filtered trend — sparklines show every evaluation, not the
  // period-collapsed representatives.
  const filteredTrend = useMemo(() => filterTrendByVisibleStandards(trend, visibleSet), [trend, visibleSet]);
  const filteredDimensions = useMemo(() => accumulatedDimensions.filter((d) => visibleSet.has((d.dimension || '').toLowerCase())), [accumulatedDimensions, visibleIds]);

  // Period-aware per-dimension trends: one entry per visible dimension,
  // { delta, scores }, bucketed by the selected granularity from the raw
  // (visible-filtered, per-run) trend. Feeds both the dimension cards and
  // the DIMENSIONS panel so their deltas/sparklines match the Overview chart.
  // The trend is sliced at the selected overview run first, so navigating to
  // a previous period truncates the series at that point in time — arrows
  // and sparklines then agree with the as-of scores on the cards. The delta
  // compares the last two buckets in which the dimension has data (carry-over
  // semantics, same as the dimmed cards).
  const asOfTrend = useMemo(
    () => sliceTrendAtRun(filteredTrend, currentOverviewRun),
    [filteredTrend, currentOverviewRun]
  );
  const dimTrends = useMemo(() => {
    const map = {};
    for (const dim of filteredDimensions) {
      const name = dim.dimension || '';
      const series = extractDimensionPeriodSeries(asOfTrend, name, granularity, DIM_SPARKLINE_LIMIT);
      const scores = series.map((s) => s.score);
      const delta = scores.length >= 2 ? scores[scores.length - 1] - scores[scores.length - 2] : null;
      map[name.toLowerCase()] = { delta, scores };
    }
    return map;
  }, [filteredDimensions, asOfTrend, granularity]);
  const filteredAccumulated = useMemo(() => filterAccumulatedByVisibleStandards(accumulated, visibleSet, filteredPeriodTrend, currentOverviewRun), [accumulated, visibleSet, filteredPeriodTrend, currentOverviewRun]);
  const filteredStats = useMemo(() => computeAccumulatedStats(filteredDimensions, filteredPeriodTrend, currentOverviewRun), [filteredDimensions, filteredPeriodTrend, currentOverviewRun]);

  // Preserve today's "panel appears iff ≥2 days of data" behavior, regardless
  // of the chosen grouping — so the selector never disappears on collapse.
  const chartMountable = filteredDayTrend.length >= 2;

  return { currentOverviewRun, selectedDayDimNames, filteredPeriodTrend, filteredTrend, filteredDimensions, filteredAccumulated, filteredStats, chartMountable, dimTrends };
}

export default function AccumulatedOverviewPanel({ data, callbacks }) {
  const { onRunClick, onDimensionClick, onNavigate } = callbacks;
  const { currentOverviewRun, selectedDayDimNames, filteredPeriodTrend, filteredTrend, filteredDimensions, filteredAccumulated, filteredStats, chartMountable, dimTrends } = useAccumulatedComputations(data);

  const topFiles = useMemo(
    () => withDimensionsStr(buildTopOffendingFiles(filteredDimensions || [])),
    [filteredDimensions]
  );

  const reportProjectName =
    data.projectInfo?.displayName
    || data.projectInfo?.name
    || data.selectedDisplayName
    || data.selectedProject
    || 'project';
  const hasReportData = Boolean(
    filteredAccumulated?.summary
    && Number.isFinite(parseFloat(filteredAccumulated.summary.numericAverage))
    && (filteredDimensions?.length ?? 0) > 0
  );
  const reportSpec = useMemo(() => {
    if (!hasReportData) return null;
    const buildMarkdown = () => buildOverviewReport(filteredAccumulated, filteredDimensions || [], reportProjectName);
    return {
      id: `report:overview:${reportProjectName}`,
      type: 'report',
      title: t('overview.reportTitle', { name: reportProjectName }),
      render: () => <ReportContent markdown={buildMarkdown()} />,
      copy: () => buildMarkdown(),
      download: () => ({ filename: `code-quality-report-${reportProjectName}.md`, body: buildMarkdown() }),
    };
  }, [hasReportData, reportProjectName, filteredAccumulated, filteredDimensions]);
  useRegisterWindowSpec('report', reportSpec);

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
