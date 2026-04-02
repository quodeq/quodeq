import { useState, useEffect, useMemo } from 'react';
import { getDimensionEval, getRescore } from '../../../api/index.js';
import TopOffendingFilesTable from '../../dashboard/components/TopOffendingFilesTable.jsx';
import ViolationsByPrincipleTable from '../../dashboard/components/ViolationsByPrincipleTable.jsx';
import CopyButton, { SparkleIcon } from '../../../components/CopyButton.jsx';
import { gradeColorClass, complianceRatio } from '../../../utils/formatters.js';
import { copyToClipboard } from '../../../utils/clipboard.js';
import { buildTopOffendingFiles, buildDimensionPlanFromViolations } from '../../../utils/explorerUtils.js';

const columnStyle = { display: 'flex', flexDirection: 'column', gap: 2 };

function computeAllViolations(evalData) {
  if (!evalData) return [];
  if (evalData.violations?.length > 0) return evalData.violations;
  return (evalData.principles || []).flatMap((p) =>
    (p.violations || []).map((v) => ({
      principle: p.name,
      file: v.file ? v.file.split(':')[0] : null,
      line: v.line || null,
      severity: v.severity || 'minor',
      reason: v.reason || v.code || '',
    }))
  );
}

function computeSeverityCounts(allViolations) {
  const counts = { critical: 0, major: 0, minor: 0 };
  allViolations.forEach((v) => {
    const s = (v.severity || 'minor').toLowerCase();
    if (counts[s] !== undefined) counts[s]++;
  });
  return counts;
}

function computeComplianceByPrinciple(evalData) {
  const map = new Map();
  for (const c of (evalData?.compliance || [])) {
    if (!map.has(c.principle)) map.set(c.principle, []);
    map.get(c.principle).push(c);
  }
  return map;
}

function DimensionOverview({ data, stats, onNavigate }) {
  const { evalData, runId, dateLabel, allViolations } = data;
  const { overallGrade, severityCounts, totalCompliant, topFiles, uniquePrinciples } = stats;
  return (
    <section className="acc-eval-panel acc-eval-panel--compact panel">
      <div className="acc-eval-top">
        <div style={columnStyle}>
          <span className="explorer-dimension-title">{evalData.dimension}</span>
          {runId && <span className="acc-eval-date">{dateLabel || runId}</span>}
        </div>
        {allViolations.length > 0 && (
          <CopyButton
            label="Full fix plan"
            className="fix-plan-btn-header"
            icon={<SparkleIcon />}
            onClick={() => copyToClipboard(buildDimensionPlanFromViolations(evalData.dimension, allViolations))}
          />
        )}
      </div>
      <div className="compact-stats-row">
        <div className="compact-score-col">
          <span className="compact-score-value">{overallGrade?.score?.replace('/10', '') || '—'}</span>
          <span className="compact-score-grade">{overallGrade?.grade || ''}</span>
        </div>
        <div className="acc-eval-stats-divider" />
        <div className="compact-metrics-col">
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Viol</span>
            <span className="acc-eval-stat-value">{allViolations.length}</span>
            <div className="acc-eval-tags">
              {severityCounts.critical > 0 && <span className="severity-tag critical">{severityCounts.critical} crit</span>}
              {severityCounts.major > 0 && <span className="severity-tag major">{severityCounts.major} maj</span>}
              {severityCounts.minor > 0 && <span className="severity-tag minor">{severityCounts.minor} min</span>}
            </div>
          </div>
          <div className="acc-eval-stats-divider" />
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Ratio</span>
            <span className="acc-eval-stat-value">{complianceRatio(allViolations.length, totalCompliant)}</span>
          </div>
          <div className="acc-eval-stats-divider" />
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Files</span>
            <span className="acc-eval-stat-value">{topFiles.length}</span>
          </div>
          <div className="acc-eval-stats-divider" />
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Principles</span>
            <span className="acc-eval-stat-value">{uniquePrinciples}</span>
          </div>
        </div>
      </div>
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
  return (
    <>
      <div className="section-header">
        <h3 className="section-title">
          {evalData.dimension.charAt(0).toUpperCase() + evalData.dimension.slice(1).toLowerCase()} Principles
        </h3>
      </div>
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
      <div className="section-header">
        <h3 className="section-title">Violations by Principle</h3>
        <span className="section-count">{allViolations.length} violations</span>
      </div>
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
      <div className="section-header">
        <h3 className="section-title">Violations by File</h3>
        <span className="section-count">{topFiles.length} files</span>
      </div>
      <section className="panel wide-panel offending-panel">
        <TopOffendingFilesTable
          files={topFiles}
          onFileClick={(f) => onNavigate && onNavigate('file', { file: f })}
        />
      </section>
    </>
  );
}

function buildEvalPrincipalFn(evalData, complianceByPrinciple) {
  return function buildEvalPrincipal(principleId) {
    const principleData = (evalData.principles || []).find((p) => p.name === principleId);
    const pg = (evalData.principleGrades || []).find((p) => p.principle === principleId);
    return {
      principle: principleId, score: pg?.score || null, grade: pg?.grade || null,
      dimension: evalData.dimension || '',
      principleData, dimViolations: principleData?.violations || [],
      dimCompliance: complianceByPrinciple.get(principleId) || [],
    };
  };
}

function useDerivedExplorerStats(evalData, allViolations) {
  const topFiles = useMemo(() => evalData ? buildTopOffendingFiles([{ dimension: evalData.dimension, violations: allViolations }]) : [], [evalData, allViolations]);
  const severityCounts = useMemo(() => computeSeverityCounts(allViolations), [allViolations]);
  const uniquePrinciples = useMemo(() => new Set(allViolations.map((v) => v.principle).filter(Boolean)).size, [allViolations]);
  const totalCompliant = useMemo(() => (evalData?.principles || []).reduce((sum, p) => sum + (p.compliance?.length || 0), 0), [evalData]);
  const complianceByPrinciple = useMemo(() => computeComplianceByPrinciple(evalData), [evalData]);
  return { topFiles, severityCounts, uniquePrinciples, totalCompliant, complianceByPrinciple };
}

function useExplorerData(project, dimension, runId) {
  const [evalData, setEvalData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  useEffect(() => {
    setLoading(true);
    getDimensionEval(project, runId, dimension)
      .then((data) => {
        setEvalData(data);
        setLoading(false);
        // Chain rescore to patch principle grades with dismissed-filtered scores
        return getRescore(project, runId).then((rescored) => {
          const dimData = (rescored.dimensions || []).find((d) => d.dimension === dimension);
          if (!dimData) return;
          setEvalData((prev) => {
            if (!prev) return prev;
            // Merge rescored principle grades and overall score
            const rescPrinciples = dimData.principles || [];
            const updatedGrades = (prev.principleGrades || []).map((pg) => {
              const match = rescPrinciples.find((rp) => rp.principle === pg.principle);
              return match ? { ...pg, score: match.score, grade: match.grade } : pg;
            });
            return {
              ...prev,
              principleGrades: updatedGrades,
              overallScore: dimData.overallScore ?? prev.overallScore,
              overallGrade: dimData.overallGrade ?? prev.overallGrade,
            };
          });
        }).catch(() => { /* rescore failure is non-fatal */ });
      })
      .catch((err) => { setError(err.message); setLoading(false); });
  }, [project, dimension, runId]);
  const overallGrade = useMemo(() => (evalData?.principleGrades || []).find((pg) => pg.isOverall || pg.principle?.includes('Overall')), [evalData]);
  const principleGrades = useMemo(() => (evalData?.principleGrades || []).filter((pg) => !pg.isOverall && !pg.principle?.includes('Overall')), [evalData]);
  const allViolations = useMemo(() => computeAllViolations(evalData), [evalData]);
  const stats = useDerivedExplorerStats(evalData, allViolations);
  return { evalData, loading, error, overallGrade, principleGrades, allViolations, ...stats };
}

export default function ExplorerPage({ project, dimension, runId, dateLabel, onNavigate }) {
  const d = useExplorerData(project, dimension, runId);
  if (d.loading) return <div className="loading" role="status" aria-live="polite">Loading…</div>;
  if (d.error) return <div className="inline-error">Failed to load evaluation data. Please try again or check the console for details.</div>;
  if (!d.evalData) return <div className="empty-state"><h2>No data found</h2></div>;
  const buildEvalPrincipal = buildEvalPrincipalFn(d.evalData, d.complianceByPrinciple);

  return (
    <>
      <DimensionOverview
        data={{ evalData: d.evalData, runId, dateLabel, allViolations: d.allViolations }}
        stats={{ overallGrade: d.overallGrade, severityCounts: d.severityCounts, totalCompliant: d.totalCompliant, topFiles: d.topFiles, uniquePrinciples: d.uniquePrinciples }}
        onNavigate={onNavigate}
      />
      <PrinciplesList evalData={d.evalData} principleGrades={d.principleGrades} onNavigate={onNavigate} buildEvalPrincipal={buildEvalPrincipal} />
      <ViolationsByPrincipleSection allViolations={d.allViolations} onNavigate={onNavigate} buildEvalPrincipal={buildEvalPrincipal} />
      <ViolationsByFileSection topFiles={d.topFiles} onNavigate={onNavigate} />
    </>
  );
}
