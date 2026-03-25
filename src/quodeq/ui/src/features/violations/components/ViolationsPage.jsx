import { useMemo, useState } from 'react';
import DimensionViolationsRow from '../../dashboard/components/DimensionViolationsRow.jsx';
import TopOffendingFilesTable from '../../dashboard/components/TopOffendingFilesTable.jsx';
import ViolationsByPrincipleTable from '../../dashboard/components/ViolationsByPrincipleTable.jsx';
import { buildTopOffendingFiles } from '../../../utils/explorerUtils.js';
import { withDimensionsStr, sortDimensionsByViolationSeverity } from '../../../utils/dimensionUtils.js';
import { complianceRatio } from '../../../utils/formatters.js';

const SUB_TABS = [
  { id: 'dimension', label: 'By Dimension' },
  { id: 'file', label: 'By File' },
];

function ViolationsPillNav({ activeSubTab, onSubTabChange }) {
  return (
    <div className="violations-pill-nav">
      {SUB_TABS.map((tab) => (
        <button
          key={tab.id}
          type="button"
          className={`pill-btn${activeSubTab === tab.id ? ' active' : ''}`}
          onClick={() => onSubTabChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

function ViolationsHeroSection({ accumulated, topFilesCount, uniquePrinciples }) {
  const summary = accumulated?.summary;
  return (
    <section className="acc-eval-panel panel">
      <div className="acc-eval-top">
        <span className="acc-eval-label">Violations</span>
      </div>
      <div className="acc-eval-stats-grid">
        <div className="acc-eval-stat-block">
          <span className="acc-eval-stat-label">Violations</span>
          <span className="acc-eval-stat-value">{summary?.totalViolations || 0}</span>
          <div className="acc-eval-tags">
            {(summary?.severity?.critical || 0) > 0 && <span className="severity-tag critical">{summary.severity.critical} critical</span>}
            {(summary?.severity?.major || 0) > 0 && <span className="severity-tag major">{summary.severity.major} major</span>}
            {(summary?.severity?.minor || 0) > 0 && <span className="severity-tag minor">{summary.severity.minor} minor</span>}
          </div>
        </div>
        <div className="acc-eval-stat-block">
          <span className="acc-eval-stat-label">Compliance</span>
          <span className="acc-eval-stat-value">{summary?.totalCompliance || 0}</span>
        </div>
        <div className="acc-eval-stat-block">
          <span className="acc-eval-stat-label">Ratio</span>
          <span className="acc-eval-stat-value">{complianceRatio(summary?.totalViolations || 0, summary?.totalCompliance || 0)}</span>
        </div>
        <div className="acc-eval-stat-block">
          <span className="acc-eval-stat-label">Files Affected</span>
          <span className="acc-eval-stat-value">{topFilesCount}</span>
        </div>
        <div className="acc-eval-stat-block">
          <span className="acc-eval-stat-label">Principles</span>
          <span className="acc-eval-stat-value">{uniquePrinciples}</span>
        </div>
        <div className="acc-eval-stat-block">
          <span className="acc-eval-stat-label">Dimensions</span>
          <span className="acc-eval-stat-value">{summary?.dimensionCount || 0}</span>
        </div>
      </div>
    </section>
  );
}

function DimensionSubTab({ dimensions, onDimensionClick, onPrincipleClick }) {
  const dimsWithViolations = useMemo(
    () => sortDimensionsByViolationSeverity(dimensions),
    [dimensions]
  );

  const violationsByPrinciple = useMemo(
    () => dimensions.flatMap((d) =>
      (d.violations || []).map((v) => ({ ...v, dimension: d.dimension }))
    ),
    [dimensions]
  );

  const uniquePrinciples = useMemo(
    () => new Set(violationsByPrinciple.map((v) => v.principle).filter(Boolean)).size,
    [violationsByPrinciple]
  );

  if (dimsWithViolations.length === 0) {
    return <p className="empty-state">No violations found.</p>;
  }

  return (
    <>
      <div className="section-header">
        <h3 className="section-title">Violations by Dimension</h3>
        <span className="section-count">{dimsWithViolations.length} dimensions</span>
      </div>
      <section className="panel violations-panel expandable">
        <div className="dimension-violations-list">
          {dimsWithViolations.map((dim) => (
            <DimensionViolationsRow
              key={dim.dimension}
              dimension={dim}
              onClick={() => onDimensionClick(dim)}
            />
          ))}
        </div>
      </section>

      {violationsByPrinciple.length > 0 && (
        <>
          <div className="section-header">
            <h3 className="section-title">Violations by Principle</h3>
            <span className="section-count">{uniquePrinciples} principles</span>
          </div>
          <section className="panel wide-panel offending-panel">
            <div className="trend-table-wrap">
              <ViolationsByPrincipleTable violations={violationsByPrinciple} onPrincipleClick={onPrincipleClick} />
            </div>
          </section>
        </>
      )}
    </>
  );
}

function FileSubTab({ dimensions, onFileClick }) {
  const topFiles = useMemo(
    () => withDimensionsStr(buildTopOffendingFiles(dimensions)),
    [dimensions]
  );

  if (topFiles.length === 0) {
    return <p className="empty-state">No file violations found.</p>;
  }

  return (
    <>
      <div className="section-header">
        <h3 className="section-title">Violations by File</h3>
        <span className="section-count">{topFiles.length} files</span>
      </div>
      <section className="panel wide-panel offending-panel">
        <div className="trend-table-wrap">
          <TopOffendingFilesTable files={topFiles} onFileClick={onFileClick} />
        </div>
      </section>
    </>
  );
}

export default function ViolationsPage({ data, callbacks }) {
  const { accumulated, accumulatedDimensions } = data;
  const { onDimensionClick, onFileClick, onPrincipleClick } = callbacks;
  const [activeSubTab, setActiveSubTab] = useState('dimension');

  const topFilesCount = useMemo(
    () => buildTopOffendingFiles(accumulatedDimensions).length,
    [accumulatedDimensions]
  );

  const uniquePrinciples = useMemo(
    () => new Set(
      accumulatedDimensions.flatMap((d) => (d.violations || []).map((v) => v.principle)).filter(Boolean)
    ).size,
    [accumulatedDimensions]
  );

  return (
    <div className="dashboard-page">
      <ViolationsHeroSection accumulated={accumulated} topFilesCount={topFilesCount} uniquePrinciples={uniquePrinciples} />
      <ViolationsPillNav activeSubTab={activeSubTab} onSubTabChange={setActiveSubTab} />
      {activeSubTab === 'dimension' && (
        <DimensionSubTab dimensions={accumulatedDimensions} onDimensionClick={onDimensionClick} onPrincipleClick={onPrincipleClick} />
      )}
      {activeSubTab === 'file' && (
        <FileSubTab dimensions={accumulatedDimensions} onFileClick={onFileClick} />
      )}
    </div>
  );
}
