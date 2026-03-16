import { useState, useEffect, useMemo } from 'react';
import { getDimensionEval } from '../../../api/index.js';
import TopOffendingFilesTable from '../../dashboard/components/TopOffendingFilesTable.jsx';
import ViolationsByPrincipleTable from '../../dashboard/components/ViolationsByPrincipleTable.jsx';
import CopyButton from '../../../components/CopyButton.jsx';
import { gradeColorClass, scoreColorClass } from '../../../utils/formatters.js';
import { buildTopOffendingFiles, buildDimensionPlanFromViolations } from '../../../utils/explorerUtils.js';

export default function ExplorerPage({ project, dimension, runId, dateLabel, onNavigate }) {
  const [evalData, setEvalData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    setLoading(true);
    getDimensionEval(project, runId, dimension)
      .then((data) => { setEvalData(data); setLoading(false); })
      .catch((err) => { setError(err.message); setLoading(false); });
  }, [project, dimension, runId]);

  // All hooks above conditional returns
  const overallGrade = useMemo(() => (evalData?.principleGrades || []).find(
    (pg) => pg.isOverall || pg.principle?.includes('Overall')
  ), [evalData]);

  const principleGrades = useMemo(() => (evalData?.principleGrades || []).filter(
    (pg) => !pg.isOverall && !pg.principle?.includes('Overall')
  ), [evalData]);

  // Top-level violations (original JSON format: {principle, file, line, severity, reason})
  const allViolations = useMemo(() => {
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
  }, [evalData]);

  // Files list via buildTopOffendingFiles (same format as overview)
  const topFiles = useMemo(() => {
    if (!evalData) return [];
    return buildTopOffendingFiles([{ dimension: evalData.dimension, violations: allViolations }]);
  }, [evalData, allViolations]);

  const severityCounts = useMemo(() => {
    const counts = { critical: 0, major: 0, minor: 0 };
    allViolations.forEach((v) => {
      const s = (v.severity || 'minor').toLowerCase();
      if (counts[s] !== undefined) counts[s]++;
    });
    return counts;
  }, [allViolations]);

  const uniquePrinciples = useMemo(
    () => new Set(allViolations.map((v) => v.principle).filter(Boolean)).size,
    [allViolations]
  );

  const totalCompliant = useMemo(
    () => (evalData?.principles || []).reduce((sum, p) => sum + (p.compliance?.length || 0), 0),
    [evalData]
  );

  const complianceByPrinciple = useMemo(() => {
    const map = new Map();
    for (const c of (evalData?.compliance || [])) {
      if (!map.has(c.principle)) map.set(c.principle, []);
      map.get(c.principle).push(c);
    }
    return map;
  }, [evalData]);

  if (loading) return <div className="loading" role="status" aria-live="polite">Loading…</div>;
  if (error) return <div className="inline-error">{error}</div>;
  if (!evalData) return <div className="empty-state"><h2>No data found</h2></div>;

  function buildEvalPrincipal(principleId) {
    const principleData = (evalData.principles || []).find((p) => p.name === principleId);
    const pg = (evalData.principleGrades || []).find((p) => p.principle === principleId);
    return {
      principle: principleId,
      score: pg?.score || null,
      grade: pg?.grade || null,
      principleData,
      dimViolations: principleData?.violations || [],
      dimCompliance: complianceByPrinciple.get(principleId) || [],
    };
  }

  return (
    <>
      <section className="acc-eval-panel acc-eval-panel--compact panel">
        <div className="acc-eval-top">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <span className="explorer-dimension-title">{evalData.dimension}</span>
            {runId && <span className="acc-eval-date">{dateLabel || runId}</span>}
          </div>
          {allViolations.length > 0 && (
            <CopyButton
              label="Fix plan"
              onClick={() => navigator.clipboard.writeText(
                buildDimensionPlanFromViolations(evalData.dimension, allViolations)
              )}
            />
          )}
        </div>

        <div className="acc-eval-hero">
          <span className={`acc-eval-grade-chip chip ${scoreColorClass(overallGrade?.score)}`}>
            {overallGrade?.grade || '—'}
          </span>
          {overallGrade?.score && (
            <div className="acc-eval-score-row">
              <span className="acc-eval-score">{overallGrade.score.replace('/10', '')}</span>
              <span className="acc-eval-score-denom">/10</span>
            </div>
          )}
        </div>

        <div className="acc-eval-stats-grid">
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Violations</span>
            <span className="acc-eval-stat-value">{allViolations.length}</span>
            <div className="acc-eval-tags">
              {severityCounts.critical > 0 && (
                <span className="severity-tag critical">{severityCounts.critical} critical</span>
              )}
              {severityCounts.major > 0 && (
                <span className="severity-tag major">{severityCounts.major} major</span>
              )}
              {severityCounts.minor > 0 && (
                <span className="severity-tag minor">{severityCounts.minor} minor</span>
              )}
            </div>
          </div>
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Compliance</span>
            <span className="acc-eval-stat-value">{totalCompliant}</span>
          </div>
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Ratio</span>
            <span className="acc-eval-stat-value">
              {(() => {
                const v = allViolations.length;
                const c = totalCompliant;
                if (v === 0) return '—';
                return `1:${(c / v).toFixed(1)}`;
              })()}
            </span>
          </div>
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Files Affected</span>
            <span className="acc-eval-stat-value">{topFiles.length}</span>
          </div>
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Principles</span>
            <span className="acc-eval-stat-value">{uniquePrinciples}</span>
          </div>
        </div>
      </section>

      {/* Principles list */}
      {principleGrades.length > 0 && (
        <>
        <div className="section-header">
          <h3 className="section-title">
            {evalData.dimension.charAt(0).toUpperCase() + evalData.dimension.slice(1).toLowerCase()} Principles
          </h3>
        </div>
        <section className="panel eval-summary-panel">
          <ul className="exec-summary-list">
            {principleGrades.map((pg) => (
              <li
                key={pg.principle}
                className="exec-summary-row exec-summary-row--clickable"
                onClick={() => onNavigate && onNavigate('evalprinciple', { evalPrincipal: buildEvalPrincipal(pg.principle) })}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onNavigate && onNavigate('evalprinciple', { evalPrincipal: buildEvalPrincipal(pg.principle) }); } }}
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
            ))}
          </ul>
        </section>
        </>
      )}

      {/* Violations by principle */}
      {allViolations.length > 0 && (
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
      )}

      {/* Violations by file — same component as main overview */}
      {topFiles.length > 0 && (
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
      )}

    </>
  );
}
