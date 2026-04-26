import { useState, useMemo, useEffect } from 'react';
import TopOffendingFilesTable from '../../dashboard/components/TopOffendingFilesTable.jsx';
import ViolationsByPrincipleTable from '../../dashboard/components/ViolationsByPrincipleTable.jsx';
import CopyButton, { SparkleIcon } from '../../../components/CopyButton.jsx';
import { gradeColorClass, complianceRatio } from '../../../utils/formatters.js';
import { copyToClipboard } from '../../../utils/clipboard.js';
import { buildTopOffendingFiles, buildDimensionPlanFromViolations } from '../../../utils/explorerUtils.js';
import { buildDimensionReport } from '../../../utils/reportBuilder.js';
import SeverityFilterPills from '../../../components/SeverityFilterPills.jsx';
import { useReportViewer } from '../../report-viewer/index.js';
import { useExplorerData, buildEvalPrincipalFn } from './explorerDataHooks.js';
import { TermHeader, StatStrip, Stat, SevBadge, SectionLabel } from '../../../components/terminal/index.js';

function DimensionOverview({ data, stats, onNavigate }) {
  const { evalData, runId, dateLabel, allViolations } = data;
  const { overallGrade, severityCounts, totalCompliant, topFiles, uniquePrinciples, principleGrades } = stats;
  const scoreDisplay = overallGrade?.score?.replace('/10', '') || '—';
  const sevBadges = (severityCounts.critical || severityCounts.major || severityCounts.minor) ? (
    <span className="principle-detail-sev-row">
      {severityCounts.critical > 0 && <SevBadge level="critical" count={severityCounts.critical} />}
      {severityCounts.major > 0    && <SevBadge level="major" count={severityCounts.major} />}
      {severityCounts.minor > 0    && <SevBadge level="minor" count={severityCounts.minor} />}
    </span>
  ) : null;

  return (
    <section className="dimension-overview dimension-overview--terminal">
      <div className="dimension-overview__top">
        <TermHeader
          name={`${evalData.dimension}.overview`}
          sub={dateLabel || runId || null}
        />
        <div className="dimension-overview__actions">
          {allViolations.length > 0 && (
            <CopyButton
              label="Full fix plan"
              className="fix-plan-btn-header"
              icon={<SparkleIcon />}
              onClick={() => copyToClipboard(buildDimensionPlanFromViolations(evalData.dimension, allViolations))}
            />
          )}
        </div>
      </div>
      <StatStrip bordered>
        <Stat label="SCORE"      value={scoreDisplay}                                      hint={overallGrade?.grade || null} />
        <Stat label="VIOLATIONS" value={allViolations.length}                              hint={sevBadges} />
        <Stat label="COMPLIANCE" value={totalCompliant} />
        <Stat label="RATIO"      value={complianceRatio(allViolations.length, totalCompliant)} />
        <Stat label="FILES"      value={topFiles.length} />
        <Stat label="PRINCIPLES" value={uniquePrinciples} />
      </StatStrip>
    </section>
  );
}

function PrincipleGradeRow({ pg, onNavigate, buildEvalPrincipal }) {
  const handleClick = () => onNavigate && onNavigate('evalprinciple', { evalPrincipal: buildEvalPrincipal(pg.principle) });
  return (
    <li
      key={pg.principle}
      className="exec-summary-row exec-summary-row--clickable"
      onClick={handleClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleClick(); } }}
    >
      <span className="exec-summary-principle">{pg.principle}</span>
      {pg.grade === 'Insufficient' ? (
        <span className="exec-summary-insufficient">Not enough evidence</span>
      ) : (
        <>
          {pg.score && (
            <span className="exec-summary-score">
              {pg.score.replace('/10', '')}<span className="exec-summary-score-denom">/10</span>
            </span>
          )}
          <span className={`chip small ${gradeColorClass(pg.grade)}`}>{pg.grade || '—'}</span>
        </>
      )}
      <span className="exec-summary-chevron">›</span>
    </li>
  );
}

function PrinciplesList({ evalData, principleGrades, onNavigate, buildEvalPrincipal }) {
  if (principleGrades.length === 0) return null;
  const dim = (evalData.dimension || '').toLowerCase();
  return (
    <>
      <SectionLabel>{`principles.${dim} · ${principleGrades.length}`}</SectionLabel>
      <section className="panel eval-summary-panel">
        <ul className="exec-summary-list">
          {principleGrades.map((pg) => (
            <PrincipleGradeRow key={pg.principle} pg={pg} onNavigate={onNavigate} buildEvalPrincipal={buildEvalPrincipal} />
          ))}
        </ul>
      </section>
    </>
  );
}

function ViolationsByPrincipleSection({ allViolations, onNavigate, buildEvalPrincipal }) {
  if (allViolations.length === 0) return null;
  return (
    <>
      <SectionLabel>violations_by_principle · {allViolations.length}</SectionLabel>
      <section className="panel wide-panel offending-panel">
        <ViolationsByPrincipleTable
          violations={allViolations}
          onPrincipleClick={(p) => onNavigate && onNavigate('evalprinciple', { evalPrincipal: buildEvalPrincipal(p.principle) })}
        />
      </section>
    </>
  );
}

function ViolationsByFileSection({ topFiles, onNavigate }) {
  if (topFiles.length === 0) return null;
  return (
    <>
      <SectionLabel>violations_by_file · {topFiles.length}</SectionLabel>
      <section className="panel wide-panel offending-panel">
        <TopOffendingFilesTable
          files={topFiles}
          onFileClick={(f) => onNavigate && onNavigate('file', { file: f })}
        />
      </section>
    </>
  );
}

export default function ExplorerPage({ project, dimension, runId, dateLabel, severityFilter, onNavigate, refreshSignal }) {
  const d = useExplorerData(project, dimension, runId, refreshSignal);
  const [activeSevFilter, setActiveSevFilter] = useState(severityFilter || null);

  // All hooks must run before any early returns (React hooks rules)
  const buildEvalPrincipal = useMemo(
    () => d.evalData ? buildEvalPrincipalFn(d.evalData, d.complianceByPrinciple, project, runId) : () => ({}),
    [d.evalData, d.complianceByPrinciple, project, runId]
  );
  const filteredViolations = useMemo(
    () => activeSevFilter
      ? d.allViolations.filter(v => (v.severity || 'minor') === activeSevFilter)
      : d.allViolations,
    [d.allViolations, activeSevFilter]
  );
  const filteredTopFiles = useMemo(
    () => activeSevFilter
      ? buildTopOffendingFiles(filteredViolations)
      : d.topFiles,
    [filteredViolations, activeSevFilter, d.topFiles]
  );

  const { setActiveBuilder, clearActiveBuilder } = useReportViewer();
  useEffect(() => {
    if (!d.evalData) {
      clearActiveBuilder();
      return undefined;
    }
    const dim = d.evalData.dimension || 'Unknown';
    const dimTitle = dim.charAt(0).toUpperCase() + dim.slice(1);
    setActiveBuilder({
      title: `${dimTitle} Report`,
      buildMarkdown: () => buildDimensionReport({
        evalData: d.evalData,
        principleGrades: d.principleGrades || [],
        allViolations: filteredViolations,
        overallGrade: d.overallGrade,
        dateLabel,
        runId,
      }),
    });
    return () => clearActiveBuilder();
  }, [setActiveBuilder, clearActiveBuilder, d.evalData, d.principleGrades, filteredViolations, d.overallGrade, dateLabel, runId]);

  if (d.loading) return <div className="loading" role="status" aria-live="polite">Loading…</div>;
  if (d.error) return <div className="inline-error">Failed to load evaluation data. Please try again or check the console for details.</div>;
  if (!d.evalData) return <div className="empty-state"><h2>No data found</h2></div>;

  return (
    <>
      <DimensionOverview
        data={{ evalData: d.evalData, runId, dateLabel, allViolations: filteredViolations }}
        stats={{ overallGrade: d.overallGrade, severityCounts: d.severityCounts, totalCompliant: d.totalCompliant, topFiles: filteredTopFiles, uniquePrinciples: d.uniquePrinciples, principleGrades: d.principleGrades }}
        onNavigate={onNavigate}
      />
      <SeverityFilterPills counts={d.severityCounts} activeFilter={activeSevFilter} onFilterChange={setActiveSevFilter} />
      <PrinciplesList evalData={d.evalData} principleGrades={d.principleGrades} onNavigate={onNavigate} buildEvalPrincipal={buildEvalPrincipal} />
      <ViolationsByPrincipleSection allViolations={filteredViolations} onNavigate={onNavigate} buildEvalPrincipal={buildEvalPrincipal} />
      <ViolationsByFileSection topFiles={filteredTopFiles} onNavigate={onNavigate} />
    </>
  );
}
