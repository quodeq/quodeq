import { useState, useMemo } from 'react';
import TopOffendingFilesTable from '../../dashboard/components/TopOffendingFilesTable.jsx';
import ViolationsByPrincipleTable from '../../dashboard/components/ViolationsByPrincipleTable.jsx';
import CopyButton, { SparkleIcon, FileTextIcon } from '../../../components/CopyButton.jsx';
import { gradeColorClass, complianceRatio } from '../../../utils/formatters.js';
import { copyToClipboard } from '../../../utils/clipboard.js';
import { buildTopOffendingFiles, buildDimensionPlanFromViolations } from '../../../utils/explorerUtils.js';
import { buildDimensionReport } from '../../../utils/reportBuilder.js';
import SeverityFilterPills from '../../../components/SeverityFilterPills.jsx';
import { useExplorerData, buildEvalPrincipalFn } from './explorerDataHooks.js';

const TOOLBAR_GAP = 8;
const columnStyle = { display: 'flex', flexDirection: 'column', gap: 2 };

function DimensionOverview({ data, stats, onNavigate }) {
  const { evalData, runId, dateLabel, allViolations } = data;
  const { overallGrade, severityCounts, totalCompliant, topFiles, uniquePrinciples, principleGrades } = stats;
  return (
    <section className="acc-eval-panel acc-eval-panel--compact panel">
      <div className="acc-eval-top">
        <div style={columnStyle}>
          <span className="explorer-dimension-title">{evalData.dimension}</span>
          {runId && <span className="acc-eval-date">{dateLabel || runId}</span>}
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'flex-start', gap: TOOLBAR_GAP }}>
          <CopyButton
            label="Report"
            className="fix-plan-btn-header"
            icon={<FileTextIcon />}
            onClick={() => copyToClipboard(buildDimensionReport({ evalData, principleGrades: principleGrades || [], allViolations, overallGrade, dateLabel, runId }))}
          />
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
