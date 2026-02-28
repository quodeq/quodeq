import { useState, useEffect, useMemo } from 'react';
import { getDimensionEval } from '../../../api/index.js';
import TopOffendingFilesTable from '../../dashboard/components/TopOffendingFilesTable.jsx';
import ViolationsByPrincipleTable from '../../dashboard/components/ViolationsByPrincipleTable.jsx';
import { gradeColorClass } from '../../../utils/formatters.js';
import { buildTopOffendingFiles } from '../../../utils/explorerUtils.js';

export default function ExplorerPage({ project, dimension, runId, onNavigate }) {
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

  if (loading) return <div className="loading">Loading…</div>;
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
      dimCompliance: principleData?.compliance || [],
    };
  }

  return (
    <div className="dashboard">
      {/* Header */}
      <section className="panel eval-header-panel">
        <div className="eval-header">
          <div>
            <p className="eval-project-label">{evalData.project}</p>
            <h2 className="eval-dimension-title">{evalData.dimension}</h2>
          </div>
          <div className="eval-header-scores">
            {overallGrade?.score && <span className="overall-score">{overallGrade.score}</span>}
            <span className={`chip ${gradeColorClass(overallGrade?.grade)}`}>
              {overallGrade?.grade || 'No grade'}
            </span>
          </div>
        </div>
        <p className="eval-meta">{evalData.runId}</p>
      </section>

      {/* Executive summary */}
      {principleGrades.length > 0 && (
        <>
          <div className="section-header">
            <h3 className="section-title">Executive Summary</h3>
          </div>
          <section className="panel eval-summary-panel">
            <ul className="exec-summary-list">
              {principleGrades.map((pg) => (
                <li
                  key={pg.principle}
                  className="exec-summary-row exec-summary-row--clickable"
                  onClick={() => onNavigate && onNavigate('evalprinciple', { evalPrincipal: buildEvalPrincipal(pg.principle) })}
                >
                  <span className="exec-summary-principle">{pg.principle}</span>
                  {pg.score && <span className="exec-summary-score">{pg.score}</span>}
                  <span className={`chip small ${gradeColorClass(pg.grade)}`}>{pg.grade || '—'}</span>
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

    </div>
  );
}
