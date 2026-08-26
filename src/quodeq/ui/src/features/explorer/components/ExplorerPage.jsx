import { useMemo, useState, useEffect } from 'react';
import TopOffendingFilesTable from '../../dashboard/components/TopOffendingFilesTable.jsx';
import { complianceRatio } from '../../../utils/formatters.js';
import { buildDimensionPlanFromViolations, buildProjectRootFile } from '../../../utils/explorerUtils.js';
import { buildDimensionReport } from '../../../utils/reportBuilder.js';
import { useRegisterWindowSpec, ReportContent } from '../../side-pane/index.js';
import { useExplorerData, buildEvalPrincipalFn } from './explorerDataHooks.js';
import { useStandardDescriptions } from '../hooks/useStandardDescriptions.js';
import {
  TermHeader,
  Stat,
  SevBadge,
  SectionLabel,
} from '../../../components/terminal/index.js';
import LoadingScreen from '../../../components/LoadingScreen.jsx';
import PrinciplesRadial from './PrinciplesRadial.jsx';
import PrinciplesCardsRow from './PrinciplesCardsRow.jsx';
import DimensionScoreHistoryPanel from './DimensionScoreHistoryPanel.jsx';
import StatGrid2x2 from './StatGrid2x2.jsx';
import { countBySeverity } from '../../../utils/severity.js';
import { t } from '../../../strings/index.js';

function buildRadialPrinciples(principleGrades) {
  return (principleGrades || []).map((pg) => {
    const score = parseFloat(pg.score);
    const hasEvidence = (pg.grade || '').toLowerCase() !== 'insufficient'
      && !Number.isNaN(score);
    return { name: pg.principle, score: hasEvidence ? score : null, hasEvidence };
  });
}

/**
 * Enrich each principleGrade with the per-principle counts that
 * DimensionGaugeCard expects: total violations, compliance count, and a
 * severity histogram. The data comes from the same evalData we already
 * have — no extra API call.
 */
function buildEnrichedPrinciples(principleGrades, allViolations, complianceByPrinciple) {
  const violationsByPrinciple = new Map();
  for (const v of allViolations || []) {
    const key = v.principle;
    if (!key) continue;
    if (!violationsByPrinciple.has(key)) violationsByPrinciple.set(key, []);
    violationsByPrinciple.get(key).push(v);
  }
  return (principleGrades || []).map((pg) => {
    const vs = violationsByPrinciple.get(pg.principle) || [];
    const severity = countBySeverity(vs);
    const compliance = complianceByPrinciple?.get?.(pg.principle) || [];
    return {
      ...pg,
      violationCount: vs.length,
      complianceCount: compliance.length,
      severity,
    };
  });
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
  // Local run/date state lets the score-history bar click swap which run
  // is shown without pushing a new entry onto the nav stack (avoids the
  // "security / security / security ..." breadcrumb pile-up). The props
  // are the source of truth when the user navigates here from elsewhere;
  // local state takes over once the user starts clicking bars.
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

  const reportSpec = useMemo(() => {
    if (!d.evalData) return null;
    const dim = (d.evalData.dimension || t('explorer.unknownDimension')).toLowerCase();
    const buildMarkdown = () => buildDimensionReport({
      evalData: d.evalData,
      principleGrades: d.principleGrades || [],
      allViolations: d.allViolations,
      overallGrade: d.overallGrade,
      dateLabel: activeDateLabel,
      runId: activeRunId,
    });
    return {
      id: `report:dimension:${dim}:${activeRunId ?? 'current'}`,
      type: 'report',
      title: t('overview.reportTitle', { name: dim }),
      render: () => <ReportContent markdown={buildMarkdown()} />,
      copy: () => buildMarkdown(),
      download: () => ({ filename: `${dim}-report.md`, body: buildMarkdown() }),
    };
  }, [d.evalData, d.principleGrades, d.allViolations, d.overallGrade, activeDateLabel, activeRunId]);
  useRegisterWindowSpec('report', reportSpec);

  const fixPlanSpec = useMemo(() => {
    if (!d.evalData || d.allViolations.length === 0) return null;
    const dim = (d.evalData.dimension || t('explorer.unknownDimension')).toLowerCase();
    const buildMarkdown = () => buildDimensionPlanFromViolations(d.evalData.dimension, d.allViolations);
    return {
      id: `fixplan:dimension:${dim}:${activeRunId ?? 'current'}`,
      type: 'fixplan',
      title: t('overview.fixPlanTitle', { name: dim }),
      render: () => <ReportContent markdown={buildMarkdown()} />,
      copy: () => buildMarkdown(),
      download: () => ({ filename: `${dim}-fix-plan.md`, body: buildMarkdown() }),
    };
  }, [d.evalData, d.allViolations, activeRunId]);
  useRegisterWindowSpec('fixplan', fixPlanSpec);

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

  const dim = String(d.evalData.dimension || '').toLowerCase();
  const radialPrinciples = buildRadialPrinciples(d.principleGrades);
  const enrichedPrinciples = buildEnrichedPrinciples(d.principleGrades, d.allViolations, d.complianceByPrinciple);
  // Thread sourceTab through: without it a principle click from a
  // Violations-tab drill-in falls back to the Overview tab, force-remounting
  // the whole content subtree (App.jsx keys it on activeTab) and jumping the
  // sidebar highlight.
  const onPrincipleClick = (name) => onNavigate?.('evalprinciple', { evalPrincipal: buildEvalPrincipal(name), sourceTab });

  const overallScoreNum = parseFloat(d.overallGrade?.score);
  const sev = d.severityCounts;
  const isRefreshing = d.isFetching && !!d.evalData;

  // Synthetic file for the dimension lets the VIOLATIONS / COMPLIANCE cards
  // (and severity badges) navigate into a FileDetailPage scoped to this
  // standard, mirroring the project / run / by-dimension-row pattern.
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
    // fromProject rides along so a file opened from a cross-project
    // explorer dismisses into ITS project, not the global selection.
    onNavigate('file', { file: dimFile, severityFilter, runId: activeRunId, dateLabel: activeDateLabel, sourceTab, fromProject: project });
  };
  const onSeverityBadge = (level) => () => handleCardNavigate(level);

  return (
    <div className={`explorer-page dashboard-fade${isRefreshing ? ' dashboard-refreshing' : ''}`}>
      <TermHeader name={dim} description={standardDescription} sub={activeDateLabel || activeRunId || null} />

      <div className="qd-top-grid">
        <div className="qd-top-left">
          <StatGrid2x2>
            <Stat
              label={t('overview.statScore')}
              value={Number.isNaN(overallScoreNum) ? '—' : overallScoreNum.toFixed(1)}
              hint={d.overallGrade?.grade ? t('overview.gradeHint', { letter: d.overallGrade.grade }) : null}
            />
            <Stat
              label={t('overview.statViolations')}
              value={d.allViolations.length}
              hint={(sev.critical || sev.major || sev.minor) ? (
                <span className="principle-detail-sev-row">
                  {sev.critical > 0 && <SevBadge level="critical" count={sev.critical} onClick={onNavigate ? onSeverityBadge('critical') : undefined} />}
                  {sev.major    > 0 && <SevBadge level="major"    count={sev.major}    onClick={onNavigate ? onSeverityBadge('major') : undefined} />}
                  {sev.minor    > 0 && <SevBadge level="minor"    count={sev.minor}    onClick={onNavigate ? onSeverityBadge('minor') : undefined} />}
                </span>
              ) : null}
              onClick={onNavigate && d.allViolations.length > 0 ? () => handleCardNavigate('violations') : undefined}
              ariaLabel={d.allViolations.length > 0 ? t('overview.showAllViolationsAria') : undefined}
            />
            <Stat
              label={t('overview.statCompliance')}
              value={d.totalCompliant}
              hint={t('overview.passingChecks', { count: d.totalCompliant + d.allViolations.length })}
              onClick={onNavigate && d.totalCompliant > 0 ? () => handleCardNavigate('compliance') : undefined}
              ariaLabel={d.totalCompliant > 0 ? t('overview.showComplianceAria') : undefined}
            />
            <Stat
              label={t('overview.statRatio')}
              value={complianceRatio(d.allViolations.length, d.totalCompliant)}
              hint={t('overview.ratioHint')}
            />
          </StatGrid2x2>

          <DimensionScoreHistoryPanel
            trend={trend}
            dimension={d.evalData.dimension}
            selectedRunId={activeRunId}
            granularity={granularity}
            onGranularityChange={onGranularityChange}
            onBarClick={(point) => {
              setActiveRunId(point.runId);
              setActiveDateLabel(point.dateLabel);
            }}
          />
        </div>

        <div className="qd-top-right">
          <section className="run-history-panel--terminal panel" aria-label={t('explorer.principlesRadialAria')}>
            <div className="run-history-panel__header">
              <SectionLabel>{t('explorer.principlesRadialLabel')} · {radialPrinciples.length}</SectionLabel>
              <span className="run-history-panel__stats">{t('explorer.scale010')}</span>
            </div>
            <div className="qd-radial">
              <PrinciplesRadial
                principles={radialPrinciples}
                onPrincipleClick={onPrincipleClick}
              />
            </div>
          </section>
        </div>
      </div>

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
