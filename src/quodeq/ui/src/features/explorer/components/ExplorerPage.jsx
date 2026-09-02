import { useMemo, useState, useEffect } from 'react';
import TopOffendingFilesTable from '../../dashboard/components/TopOffendingFilesTable.jsx';
import { buildProjectRootFile } from '../../../utils/explorerUtils.js';
import { useExplorerData, buildEvalPrincipalFn } from './explorerDataHooks.js';
import { useStandardDescriptions } from '../hooks/useStandardDescriptions.js';
import { TermHeader, SectionLabel } from '../../../components/terminal/index.js';
import LoadingScreen from '../../../components/LoadingScreen.jsx';
import PrinciplesCardsRow from './PrinciplesCardsRow.jsx';
import ExplorerStatsPanel from './ExplorerStatsPanel.jsx';
import ExplorerRadialPanel from './ExplorerRadialPanel.jsx';
import { useExplorerPageSpecs } from './useExplorerPageSpecs.jsx';
import { buildRadialPrinciples, buildEnrichedPrinciples } from './explorerPrincipleView.js';
import { t } from '../../../strings/index.js';

/** Empty/loading/error states, checked in order — extracted so the main
 * render stays a single happy-path return. */
function explorerPageStatus(d) {
  if (d.loading) return <LoadingScreen />;
  if (d.error) return <div className="inline-error">{t('explorer.loadFailed')}</div>;
  if (d.waiting) {
    // 202 from the backend: the run exists but this dimension's report
    // isn't written (still running, or the run stopped before reaching it).
    // Rendering it as data would show SCORE — / 0 violations and read as a
    // clean pass.
    return (
      <div className="empty-state">
        <h2>{t('explorer.reportNotReadyTitle')}</h2>
        <p>{t('explorer.reportNotReadyBody')}</p>
      </div>
    );
  }
  if (!d.evalData) return <div className="empty-state"><h2>{t('explorer.noDataFound')}</h2></div>;
  return null;
}

/**
 * The fetched data + the local run/date override. Local state lets the
 * score-history bar click swap which run is shown without pushing a new
 * entry onto the nav stack (avoids the "security / security / security ..."
 * breadcrumb pile-up). The props are the source of truth when the user
 * navigates here from elsewhere; local state takes over once the user
 * starts clicking bars.
 */
function useExplorerPageData(project, dimension, runId, dateLabel, refreshSignal, selectedSource) {
  const [activeRunId, setActiveRunId] = useState(runId);
  const [activeDateLabel, setActiveDateLabel] = useState(dateLabel);
  useEffect(() => { setActiveRunId(runId); }, [runId]);
  useEffect(() => { setActiveDateLabel(dateLabel); }, [dateLabel]);
  const d = useExplorerData(project, dimension, activeRunId, refreshSignal, selectedSource);
  const { standardDescription } = useStandardDescriptions(dimension);

  const buildEvalPrincipal = useMemo(
    () => d.evalData ? buildEvalPrincipalFn(d.evalData, d.complianceByPrinciple, project, activeRunId, activeDateLabel) : () => ({}),
    [d.evalData, d.complianceByPrinciple, project, activeRunId, activeDateLabel]
  );

  return { d, standardDescription, activeRunId, setActiveRunId, activeDateLabel, setActiveDateLabel, buildEvalPrincipal };
}

/**
 * The synthetic dimension-root file the VIOLATIONS / COMPLIANCE cards (and
 * severity badges) navigate into a FileDetailPage with, mirroring the
 * project / run / by-dimension-row pattern. fromProject rides along so a
 * file opened from a cross-project explorer dismisses into ITS project,
 * not the global selection.
 */
function buildExplorerCardNavigation({ d, onNavigate, project, activeRunId, activeDateLabel, sourceTab }) {
  const allCompliance = [];
  if (d.complianceByPrinciple) {
    for (const items of d.complianceByPrinciple.values()) allCompliance.push(...items);
  }
  const dimFile = buildProjectRootFile(
    [{ dimension: d.evalData.dimension, violations: d.allViolations, compliance: allCompliance }],
    d.evalData.dimension,
  );
  const handleCardNavigate = (kind) => {
    if (!onNavigate) return;
    const severityFilter = kind === 'violations' ? 'all' : kind;
    onNavigate('file', { file: dimFile, severityFilter, runId: activeRunId, dateLabel: activeDateLabel, sourceTab, fromProject: project });
  };
  const onSeverityBadge = (level) => () => handleCardNavigate(level);
  return { handleCardNavigate, onSeverityBadge };
}

/** Top grid: the stats panel (score/violations/compliance/history) plus
 * the principles radial. */
function ExplorerTopGrid({
  overallScoreNum, d, onSeverityBadge, onNavigate, handleCardNavigate, trend, granularity,
  onGranularityChange, setActiveRunId, setActiveDateLabel, activeRunId, radialPrinciples, onPrincipleClick,
}) {
  return (
    <div className="qd-top-grid">
      <ExplorerStatsPanel
        overallScoreNum={overallScoreNum}
        overallGrade={d.overallGrade}
        allViolations={d.allViolations}
        totalCompliant={d.totalCompliant}
        sev={d.severityCounts}
        onSeverityBadge={onSeverityBadge}
        onNavigate={onNavigate}
        onCardNavigate={handleCardNavigate}
        trend={trend}
        dimension={d.evalData.dimension}
        activeRunId={activeRunId}
        granularity={granularity}
        onGranularityChange={onGranularityChange}
        onBarClick={(point) => {
          setActiveRunId(point.runId);
          setActiveDateLabel(point.dateLabel);
        }}
      />
      <ExplorerRadialPanel radialPrinciples={radialPrinciples} onPrincipleClick={onPrincipleClick} />
    </div>
  );
}

/** The happy-path render: header, top grid (stats + radial), principle
 * cards, and the top-offending-files table. */
function ExplorerPageBody({
  isRefreshing, dim, standardDescription, activeDateLabel, activeRunId, overallScoreNum, d,
  onSeverityBadge, onNavigate, handleCardNavigate, trend, granularity, onGranularityChange,
  setActiveRunId, setActiveDateLabel, radialPrinciples, onPrincipleClick, enrichedPrinciples,
  sourceTab, project,
}) {
  return (
    <div className={`explorer-page dashboard-fade${isRefreshing ? ' dashboard-refreshing' : ''}`}>
      <TermHeader name={dim} description={standardDescription} sub={activeDateLabel || activeRunId || null} />

      <ExplorerTopGrid
        overallScoreNum={overallScoreNum} d={d} onSeverityBadge={onSeverityBadge} onNavigate={onNavigate}
        handleCardNavigate={handleCardNavigate} trend={trend} granularity={granularity}
        onGranularityChange={onGranularityChange} setActiveRunId={setActiveRunId} setActiveDateLabel={setActiveDateLabel}
        activeRunId={activeRunId} radialPrinciples={radialPrinciples} onPrincipleClick={onPrincipleClick}
      />

      <section className="qd-cards-panel" aria-label={t('explorer.principlesAria')}>
        <div className="qd-cards-panel__head">
          <SectionLabel>{t('explorer.principlesLabel')} · {radialPrinciples.length}</SectionLabel>
        </div>
        <PrinciplesCardsRow
          principles={enrichedPrinciples}
          onPrincipleClick={onPrincipleClick}
        />
      </section>

      <section className="qd-cards-panel offending-panel" aria-label={t('overview.violationsByFileAria')}>
        <div className="qd-cards-panel__head">
          <SectionLabel>{t('overview.violationsByFileLabel')} · {d.topFiles.length}</SectionLabel>
          <span className="run-history-panel__stats">{t('overview.sortedBySeverity')}</span>
        </div>
        <TopOffendingFilesTable
          files={d.topFiles}
          onFileClick={(f) => onNavigate?.('file', { file: f, runId: activeRunId, dateLabel: activeDateLabel, sourceTab, fromProject: project })}
        />
      </section>
    </div>
  );
}

/** The values derived from `d` once it's known to be ready (dim label,
 * radial/enriched principle views, the principle-click handler, score,
 * refreshing flag). Thread sourceTab through onPrincipleClick: without it a
 * principle click from a Violations-tab drill-in falls back to the
 * Overview tab, force-remounting the whole content subtree (App.jsx keys
 * it on activeTab) and jumping the sidebar highlight. */
function buildExplorerViewData(d, onNavigate, sourceTab, buildEvalPrincipal) {
  return {
    dim: String(d.evalData.dimension || '').toLowerCase(),
    radialPrinciples: buildRadialPrinciples(d.principleGrades),
    enrichedPrinciples: buildEnrichedPrinciples(d.principleGrades, d.allViolations, d.complianceByPrinciple),
    onPrincipleClick: (name) => onNavigate?.('evalprinciple', { evalPrincipal: buildEvalPrincipal(name), sourceTab }),
    overallScoreNum: parseFloat(d.overallGrade?.score),
    isRefreshing: d.isFetching && !!d.evalData,
  };
}

export default function ExplorerPage({
  project,
  dimension,
  runId,
  dateLabel,
  sourceTab,
  selectedSource = 'local',
  onNavigate,
  refreshSignal,
  trend = [],
  granularity = 'day',
  onGranularityChange,
}) {
  const { d, standardDescription, activeRunId, setActiveRunId, activeDateLabel, setActiveDateLabel, buildEvalPrincipal } =
    useExplorerPageData(project, dimension, runId, dateLabel, refreshSignal, selectedSource);

  useExplorerPageSpecs({
    evalData: d.evalData, principleGrades: d.principleGrades, allViolations: d.allViolations,
    overallGrade: d.overallGrade, activeDateLabel, activeRunId,
  });

  const status = explorerPageStatus(d);
  if (status) return status;

  const { handleCardNavigate, onSeverityBadge } = buildExplorerCardNavigation({
    d, onNavigate, project, activeRunId, activeDateLabel, sourceTab,
  });

  const {
    dim, radialPrinciples, enrichedPrinciples, onPrincipleClick, overallScoreNum, isRefreshing,
  } = buildExplorerViewData(d, onNavigate, sourceTab, buildEvalPrincipal);

  return (
    <ExplorerPageBody
      isRefreshing={isRefreshing} dim={dim} standardDescription={standardDescription}
      activeDateLabel={activeDateLabel} activeRunId={activeRunId} overallScoreNum={overallScoreNum} d={d}
      onSeverityBadge={onSeverityBadge} onNavigate={onNavigate} handleCardNavigate={handleCardNavigate}
      trend={trend} granularity={granularity} onGranularityChange={onGranularityChange}
      setActiveRunId={setActiveRunId} setActiveDateLabel={setActiveDateLabel}
      radialPrinciples={radialPrinciples} onPrincipleClick={onPrincipleClick} enrichedPrinciples={enrichedPrinciples}
      sourceTab={sourceTab} project={project}
    />
  );
}
