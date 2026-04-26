import { useMemo, lazy, Suspense, useEffect } from 'react';
import TrendBadge from '../../../components/TrendBadge.jsx';
import DimensionCardsGrid from './DimensionCardsGrid.jsx';
import { formatRunId, gradeLetter, complianceRatio, extDisplayName } from '../../../utils/formatters.js';
import { collapseByDay, collectDayDimensions } from '../../../utils/dailyGrouping.js';
const RunHistoryPanel = lazy(() => import('./RunHistoryPanel.jsx'));
import DimensionScorePanel from './DimensionScorePanel.jsx';
import TopFindings from './TopFindings.jsx';
import { TermHeader, StatStrip, Stat, SevBadge, SectionLabel } from '../../../components/terminal/index.js';

import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';
import { filterTrendByVisibleStandards, filterTrendByVisibleStandardsDaily, filterAccumulatedByVisibleStandards } from '../../../utils/scoreFiltering.js';
import { useReportViewer } from '../../report-viewer/index.js';
import { buildOverviewReport } from '../../../utils/reportBuilder.js';

// ---------------------------------------------------------------------------
// Accumulated overview panel helpers
// ---------------------------------------------------------------------------

function computeAccumulatedStats(accumulated, accumulatedDimensions, dailyTrend, selectedRunId) {
  const curr = parseFloat(accumulated?.summary?.numericAverage);
  let scoreDelta = null;
  if (dailyTrend && dailyTrend.length >= 2) {
    const selectedIdx = selectedRunId ? dailyTrend.findIndex((t) => t.runId === selectedRunId) : 0;
    const idx = selectedIdx >= 0 ? selectedIdx : 0;
    const current = parseFloat(dailyTrend[idx]?.numericAverage);
    const previous = idx + 1 < dailyTrend.length ? parseFloat(dailyTrend[idx + 1]?.numericAverage) : NaN;
    if (!Number.isNaN(current) && !Number.isNaN(previous)) scoreDelta = (current - previous).toFixed(1);
  }
  if (scoreDelta === null) {
    const prev = parseFloat(accumulated?.summary?.previousNumericAverage);
    scoreDelta = (Number.isNaN(curr) || Number.isNaN(prev)) ? null : (curr - prev).toFixed(1);
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

function SeverityBadgeRow({ severity }) {
  const sev = severity || {};
  if (!(sev.critical || sev.major || sev.minor)) return null;
  return (
    <span className="acc-eval-sev-row">
      {sev.critical > 0 && <SevBadge level="critical" count={sev.critical} format="count-abbr" />}
      {sev.major > 0    && <SevBadge level="major"    count={sev.major}    format="count-abbr" />}
      {sev.minor > 0    && <SevBadge level="minor"    count={sev.minor}    format="count-abbr" />}
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

function AccumulatedHeroSection({ accumulated, scoreDelta, lastDate, accumulatedDimensions, projectName, projectInfo }) {
  const summary = accumulated?.summary;
  const scoreNum = parseFloat(summary?.numericAverage);
  const scoreDisplay = isNaN(scoreNum) ? '—' : scoreNum.toFixed(1);
  const grade = summary?.overallGrade;
  const violations = summary?.totalViolations || 0;
  const compliance = summary?.totalCompliance || 0;
  const totalChecks = violations + compliance;
  const ratio = complianceRatio(violations, compliance);

  return (
    <section className="acc-eval-panel acc-eval-panel--terminal">
      <div className="acc-eval-panel__top">
        <TermHeader
          name="overview"
          sub={buildLanguageSub(projectInfo) || (lastDate ? `last_evaluated · ${lastDate}` : null)}
        />
      </div>
      <StatStrip cards>
        <Stat
          label="SCORE"
          value={scoreDisplay}
          trailing={scoreDelta !== null ? <TrendBadge delta={scoreDelta} showLabel={false} /> : null}
          hint={grade ? `grade ${gradeLetter(grade)}` : null}
        />
        <Stat
          label="VIOLATIONS"
          value={violations}
          hint={<SeverityBadgeRow severity={summary?.severity} />}
        />
        <Stat
          label="COMPLIANCE"
          value={compliance}
          hint={totalChecks > 0 ? `passing / ${totalChecks} checks` : null}
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

function AccumulatedDimensionsSection({ sortedDimensions, onDimensionClick, selectedDayDimNames }) {
  return (
    <section className="quality-dimensions" aria-label="Quality dimensions">
      <div className="quality-dimensions__head">
        <SectionLabel>quality_dimensions · {sortedDimensions.length}</SectionLabel>
      </div>
      <div className="dimensions-panel">
        <DimensionCardsGrid
          sortedDimensions={sortedDimensions}
          onDimensionClick={onDimensionClick}
          selectedDayDimNames={selectedDayDimNames}
        />
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Accumulated overview panel
// ---------------------------------------------------------------------------

function useAccumulatedComputations(data) {
  const { accumulated, accumulatedDimensions, availableRuns, dailyRuns, overviewRunIndex, trend, selectedRunId } = data;
  const dayRuns = dailyRuns || availableRuns;
  const dailyTrend = useMemo(() => collapseByDay(trend), [trend]);

  const effectiveSelectedId = useMemo(() => {
    if (!selectedRunId || !trend.length) return dailyTrend[0]?.runId || null;
    const direct = dailyTrend.find((t) => t.runId === selectedRunId);
    if (direct) return direct.runId;
    const rawEntry = trend.find((t) => t.runId === selectedRunId);
    if (rawEntry) {
      const datePart = (rawEntry.dateISO || '').slice(0, 10);
      const dayEntry = dailyTrend.find((t) => (t.dateISO || '').slice(0, 10) === datePart);
      if (dayEntry) return dayEntry.runId;
    }
    return dailyTrend[0]?.runId || null;
  }, [selectedRunId, trend, dailyTrend]);

  const currentOverviewRun = effectiveSelectedId || dayRuns[overviewRunIndex]?.runId || 'latest';
  const selectedDayDimNames = useMemo(
    () => collectDayDimensions(trend, currentOverviewRun) || collectDayDimensions(trend, selectedRunId),
    [trend, currentOverviewRun, selectedRunId]
  );

  const visibleIds = useMemo(() => readVisibleStandardIds(), [accumulatedDimensions]);
  const visibleSet = useMemo(() => new Set(visibleIds), [visibleIds]);
  const filteredDailyTrend = useMemo(() => filterTrendByVisibleStandardsDaily(trend, dailyTrend, visibleSet), [trend, dailyTrend, visibleSet]);
  // Raw (per-run) filtered trend — needed by the dimension sparklines so they
  // can show every evaluation where the standard was measured, not only the
  // daily-collapsed representatives.
  const filteredTrend = useMemo(() => filterTrendByVisibleStandards(trend, visibleSet), [trend, visibleSet]);
  const filteredDimensions = useMemo(() => accumulatedDimensions.filter((d) => visibleSet.has((d.dimension || '').toLowerCase())), [accumulatedDimensions, visibleIds]);
  const filteredAccumulated = useMemo(() => filterAccumulatedByVisibleStandards(accumulated, visibleSet, filteredDailyTrend, currentOverviewRun), [accumulated, visibleSet, filteredDailyTrend, currentOverviewRun]);
  const filteredStats = useMemo(() => computeAccumulatedStats(filteredAccumulated, filteredDimensions, filteredDailyTrend, currentOverviewRun), [filteredAccumulated, filteredDimensions, filteredDailyTrend, currentOverviewRun]);

  return { currentOverviewRun, selectedDayDimNames, filteredDailyTrend, filteredTrend, filteredDimensions, filteredAccumulated, filteredStats };
}

export default function AccumulatedOverviewPanel({ data, callbacks }) {
  const { onRunClick, onDimensionClick, onNavigate } = callbacks;
  const { currentOverviewRun, selectedDayDimNames, filteredDailyTrend, filteredTrend, filteredDimensions, filteredAccumulated, filteredStats } = useAccumulatedComputations(data);

  const { setActiveBuilder, clearActiveBuilder } = useReportViewer();
  useEffect(() => {
    setActiveBuilder({
      title: `Code Quality Report — ${data.selectedProject || 'project'}`,
      buildMarkdown: () => buildOverviewReport(filteredAccumulated, filteredDimensions || [], data.selectedProject),
    });
    return () => clearActiveBuilder();
  }, [setActiveBuilder, clearActiveBuilder, data.selectedProject, filteredAccumulated, filteredDimensions]);

  return (
    <>
      <AccumulatedHeroSection
        accumulated={filteredAccumulated}
        scoreDelta={filteredStats.scoreDelta}
        lastDate={filteredStats.lastRun.date}
        accumulatedDimensions={filteredDimensions}
        projectName={data.selectedProject}
        projectInfo={data.projectInfo}
      />

      <div className="history-panels-row">
        <Suspense fallback={null}>
          <RunHistoryPanel trend={filteredDailyTrend} selectedRunId={currentOverviewRun} onBarClick={onRunClick} />
        </Suspense>
        <DimensionScorePanel dimensions={filteredDimensions} onBarClick={onDimensionClick} runDate={filteredStats.lastRun.date} runId={filteredStats.lastRun.runId} trend={filteredTrend} />
      </div>

      <AccumulatedDimensionsSection
        sortedDimensions={filteredStats.sorted}
        onDimensionClick={onDimensionClick}
        selectedDayDimNames={selectedDayDimNames}
      />

      <TopFindings
        dimensions={filteredDimensions}
        onFindingClick={(f) => {
          if (onNavigate) {
            onNavigate('finding', {
              finding: f,
              dimension: f._dim,
              principle: f.principle,
            });
          } else if (onDimensionClick) {
            onDimensionClick({ dimension: f._dim, fromRunId: filteredStats.lastRun.runId, fromDateLabel: filteredStats.lastRun.date });
          }
        }}
      />
    </>
  );
}
