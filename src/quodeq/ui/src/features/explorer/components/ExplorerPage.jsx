import { useMemo } from 'react';
import TopOffendingFilesTable from '../../dashboard/components/TopOffendingFilesTable.jsx';
import { complianceRatio } from '../../../utils/formatters.js';
import { buildDimensionPlanFromViolations } from '../../../utils/explorerUtils.js';
import { buildDimensionReport } from '../../../utils/reportBuilder.js';
import { useRegisterWindowSpec, ReportContent } from '../../side-pane/index.js';
import { useExplorerData, buildEvalPrincipalFn } from './explorerDataHooks.js';
import {
  TermHeader,
  Stat,
  SevBadge,
  SectionLabel,
} from '../../../components/terminal/index.js';
import PrinciplesRadial from './PrinciplesRadial.jsx';
import PrinciplesCardsRow from './PrinciplesCardsRow.jsx';
import DimensionScoreHistoryPanel from './DimensionScoreHistoryPanel.jsx';
import StatGrid2x2 from './StatGrid2x2.jsx';

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
    const severity = { critical: 0, major: 0, minor: 0 };
    for (const v of vs) {
      const s = (v.severity || 'minor').toLowerCase();
      if (severity[s] !== undefined) severity[s]++;
    }
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
  onNavigate,
  refreshSignal,
  trend = [],
}) {
  const d = useExplorerData(project, dimension, runId, refreshSignal);

  const buildEvalPrincipal = useMemo(
    () => d.evalData ? buildEvalPrincipalFn(d.evalData, d.complianceByPrinciple, project, runId) : () => ({}),
    [d.evalData, d.complianceByPrinciple, project, runId]
  );

  const reportSpec = useMemo(() => {
    if (!d.evalData) return null;
    const dim = (d.evalData.dimension || 'unknown').toLowerCase();
    const buildMarkdown = () => buildDimensionReport({
      evalData: d.evalData,
      principleGrades: d.principleGrades || [],
      allViolations: d.allViolations,
      overallGrade: d.overallGrade,
      dateLabel,
      runId,
    });
    return {
      id: `report:dimension:${dim}:${runId ?? 'current'}`,
      type: 'report',
      title: `${dim} report`,
      render: () => <ReportContent markdown={buildMarkdown()} />,
      copy: () => buildMarkdown(),
      download: () => ({ filename: `${dim}-report.md`, body: buildMarkdown() }),
    };
  }, [d.evalData, d.principleGrades, d.allViolations, d.overallGrade, dateLabel, runId]);
  useRegisterWindowSpec('report', reportSpec);

  const fixPlanSpec = useMemo(() => {
    if (!d.evalData || d.allViolations.length === 0) return null;
    const dim = (d.evalData.dimension || 'unknown').toLowerCase();
    const buildMarkdown = () => buildDimensionPlanFromViolations(d.evalData.dimension, d.allViolations);
    return {
      id: `fixplan:dimension:${dim}:${runId ?? 'current'}`,
      type: 'fixplan',
      title: `${dim} fix plan`,
      render: () => <ReportContent markdown={buildMarkdown()} />,
      copy: () => buildMarkdown(),
      download: () => ({ filename: `${dim}-fix-plan.md`, body: buildMarkdown() }),
    };
  }, [d.evalData, d.allViolations, runId]);
  useRegisterWindowSpec('fixplan', fixPlanSpec);

  if (d.loading) return <div className="loading" role="status" aria-live="polite">Loading…</div>;
  if (d.error) return <div className="inline-error">Failed to load evaluation data. Please try again or check the console for details.</div>;
  if (!d.evalData) return <div className="empty-state"><h2>No data found</h2></div>;

  const dim = String(d.evalData.dimension || '').toLowerCase();
  const radialPrinciples = buildRadialPrinciples(d.principleGrades);
  const enrichedPrinciples = buildEnrichedPrinciples(d.principleGrades, d.allViolations, d.complianceByPrinciple);
  const onPrincipleClick = (name) => onNavigate?.('evalprinciple', { evalPrincipal: buildEvalPrincipal(name) });

  const overallScoreNum = parseFloat(d.overallGrade?.score);
  const sev = d.severityCounts;

  return (
    <>
      <TermHeader name={`${dim}.overview`} sub={dateLabel || runId || null} />

      <div className="qd-top-grid">
        <div className="qd-top-left">
          <StatGrid2x2>
            <Stat
              label="SCORE"
              value={Number.isNaN(overallScoreNum) ? '—' : overallScoreNum.toFixed(1)}
              hint={d.overallGrade?.grade ? `grade ${d.overallGrade.grade}` : null}
            />
            <Stat
              label="VIOLATIONS"
              value={d.allViolations.length}
              hint={(sev.critical || sev.major || sev.minor) ? (
                <span className="principle-detail-sev-row">
                  {sev.critical > 0 && <SevBadge level="critical" count={sev.critical} />}
                  {sev.major    > 0 && <SevBadge level="major"    count={sev.major} />}
                  {sev.minor    > 0 && <SevBadge level="minor"    count={sev.minor} />}
                </span>
              ) : null}
            />
            <Stat
              label="COMPLIANCE"
              value={d.totalCompliant}
              hint={`passing / ${d.totalCompliant + d.allViolations.length} checks`}
            />
            <Stat
              label="RATIO"
              value={complianceRatio(d.allViolations.length, d.totalCompliant)}
              hint="compliance : violations"
            />
          </StatGrid2x2>

          <DimensionScoreHistoryPanel trend={trend} dimension={d.evalData.dimension} />
        </div>

        <div className="qd-top-right">
          <section className="run-history-panel--terminal panel" aria-label="Principles radial">
            <div className="run-history-panel__header">
              <SectionLabel>principles_radial · {radialPrinciples.length}</SectionLabel>
              <span className="run-history-panel__stats">SCALE 0–10</span>
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

      <section className="qd-cards-panel" aria-label="Principles">
        <div className="qd-cards-panel__head">
          <SectionLabel>{`principles · ${radialPrinciples.length}`}</SectionLabel>
        </div>
        <PrinciplesCardsRow
          principles={enrichedPrinciples}
          onPrincipleClick={onPrincipleClick}
        />
      </section>

      <section className="qd-cards-panel offending-panel" aria-label="Violations by file">
        <div className="qd-cards-panel__head">
          <SectionLabel>{`violations_by_file · ${d.topFiles.length}`}</SectionLabel>
          <span className="run-history-panel__stats">SORTED BY SEVERITY</span>
        </div>
        <TopOffendingFilesTable
          files={d.topFiles}
          onFileClick={(f) => onNavigate?.('file', { file: f })}
        />
      </section>
    </>
  );
}
