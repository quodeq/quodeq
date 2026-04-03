import { useCallback, useEffect, useMemo, useState } from 'react';
import DimensionViolationsRow from '../../dashboard/components/DimensionViolationsRow.jsx';
import TopOffendingFilesTable from '../../dashboard/components/TopOffendingFilesTable.jsx';
import ViolationsByPrincipleTable from '../../dashboard/components/ViolationsByPrincipleTable.jsx';
import { listDismissedFindings, restoreFinding, restoreAllFindings } from '../../../api/index.js';
import ContextBlock from '../../../components/ContextBlock.jsx';
import { buildTopOffendingFiles } from '../../../utils/explorerUtils.js';
import { withDimensionsStr, sortDimensionsByViolationSeverity } from '../../../utils/dimensionUtils.js';
import { complianceRatio } from '../../../utils/formatters.js';
import { readVisibleStandardIds, computeSummaryFromDimensions } from '../../../utils/visibleStandards.js';

function ViolationsPillNav({ activeSubTab, onSubTabChange, dismissedCount }) {
  const tabs = [
    { id: 'dimension', label: 'By Dimension' },
    { id: 'file', label: 'By File' },
  ];
  if (dismissedCount > 0) {
    tabs.push({ id: 'dismissed', label: `Dismissed (${dismissedCount})` });
  }
  return (
    <div className="violations-pill-nav">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          className={`pill-btn${activeSubTab === tab.id ? ' active' : ''}${tab.id === 'dismissed' ? ' pill-btn--dismissed' : ''}`}
          onClick={() => onSubTabChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

function ViolationsHeader({ accumulated, topFilesCount, uniquePrinciples }) {
  const summary = accumulated?.summary;
  return (
    <>
      <div className="page-header">
        <h2 className="page-title">Violations</h2>
      </div>
      <section className="panel violations-stats-panel">
        <div className="violations-stats-grid">
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
    </>
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

function DismissedSubTab({ dismissed, onRestore, onRestoreAll }) {
  if (dismissed.length === 0) {
    return <p className="empty-state">No dismissed findings.</p>;
  }
  return (
    <>
      <div className="section-header">
        <h3 className="section-title">Dismissed Findings</h3>
        <span className="section-count">{dismissed.length} findings · not included in scoring</span>
        {dismissed.length > 1 && (
          <button type="button" className="restore-btn" style={{ marginLeft: 'auto' }} onClick={onRestoreAll}>
            Restore all
          </button>
        )}
      </div>
      <div className="dismissed-list-inner">
        {dismissed.map((d) => (
          <div key={`${d.req}-${d.file}-${d.line}`} className="dismissed-card">
            <div className="dismissed-card-top">
              <span className="dismissed-tag">dismissed</span>
              {d.severity && <span className={`severity-tag ${d.severity}`}>{d.severity}</span>}
              <span className="dismissed-label">[{d.principle || d.dimension || d.req || '?'}]</span>
              <span className="dismissed-file">{d.file}:{d.line}</span>
              <button type="button" className="restore-btn" onClick={() => onRestore(d)}>Restore</button>
            </div>
            {(d.reason || d.title) && (
              <div className="dismissed-detail">
                {d.title && (
                  <div className="dismissed-detail-section">
                    <div className="dismissed-detail-header">
                      <span className="dismissed-detail-label">Reason</span>
                      {(d.reqRefs || []).filter((r) => r.url && /^https?:\/\//.test(r.url)).length > 0 && (
                        <span className="cwe-link-group">
                          {d.reqRefs.filter((r) => r.url && /^https?:\/\//.test(r.url)).map((r, i) => (
                            <a key={i} className="cwe-link" href={r.url} target="_blank" rel="noopener noreferrer">{r.label}</a>
                          ))}
                        </span>
                      )}
                    </div>
                    <p className="dismissed-detail-title">{d.title}</p>
                  </div>
                )}
                {d.reason && (
                  <div className="dismissed-detail-section">
                    <span className="dismissed-detail-label">Detail</span>
                    <p className="dismissed-detail-text">{d.reason}</p>
                  </div>
                )}
                <ContextBlock context={d.context} snippet={d.snippet} scope={d.scope} line={d.line} endLine={d.endLine} />
              </div>
            )}
          </div>
        ))}
      </div>
    </>
  );
}

export default function ViolationsPage({ data, callbacks }) {
  const { accumulated, accumulatedDimensions, selectedProject } = data;
  const { onDimensionClick, onFileClick, onPrincipleClick, onRefresh } = callbacks;
  const [activeSubTab, setActiveSubTab] = useState('dimension');
  const [dismissed, setDismissed] = useState([]);

  useEffect(() => {
    if (!selectedProject) return;
    listDismissedFindings(selectedProject).then(setDismissed).catch(() => setDismissed([]));
  }, [selectedProject]);

  const handleRestore = useCallback(async (d) => {
    try {
      await restoreFinding(selectedProject, { req: d.req, file: d.file, line: d.line });
      setDismissed((prev) => prev.filter((item) => !(item.req === d.req && item.file === d.file && item.line === d.line)));
      onRefresh?.();
    } catch (err) {
      console.error('Failed to restore finding:', err);
    }
  }, [selectedProject, onRefresh]);

  const handleRestoreAll = useCallback(async () => {
    try {
      await restoreAllFindings(selectedProject);
      setDismissed([]);
      onRefresh?.();
    } catch (err) {
      console.error('Failed to restore all findings:', err);
    }
  }, [selectedProject, onRefresh]);

  const visibleDimensions = useMemo(() => {
    const visibleSet = new Set(readVisibleStandardIds());
    return accumulatedDimensions.filter((d) => visibleSet.has((d.dimension || '').toLowerCase()));
  }, [accumulatedDimensions]);

  const topFilesCount = useMemo(
    () => new Set(
      visibleDimensions.flatMap((d) => (d.violations || []).map((v) => v.file)).filter(Boolean)
    ).size,
    [visibleDimensions]
  );

  const uniquePrinciples = useMemo(
    () => new Set(
      visibleDimensions.flatMap((d) => (d.violations || []).map((v) => v.principle)).filter(Boolean)
    ).size,
    [visibleDimensions]
  );

  const filteredAccumulated = useMemo(() => {
    if (!accumulated) return accumulated;
    const { totalViolations, totalCompliance, severity } = computeSummaryFromDimensions(visibleDimensions);
    return {
      ...accumulated,
      summary: {
        ...accumulated.summary,
        totalViolations,
        totalCompliance,
        dimensionCount: visibleDimensions.length,
        severity,
      },
    };
  }, [accumulated, visibleDimensions]);

  return (
    <div className="violations-page">
      <ViolationsHeader accumulated={filteredAccumulated} topFilesCount={topFilesCount} uniquePrinciples={uniquePrinciples} />
      <ViolationsPillNav activeSubTab={activeSubTab} onSubTabChange={setActiveSubTab} dismissedCount={dismissed.length} />
      {activeSubTab === 'dimension' && (
        <DimensionSubTab dimensions={visibleDimensions} onDimensionClick={onDimensionClick} onPrincipleClick={onPrincipleClick} />
      )}
      {activeSubTab === 'file' && (
        <FileSubTab dimensions={visibleDimensions} onFileClick={onFileClick} />
      )}
      {activeSubTab === 'dismissed' && (
        <DismissedSubTab dismissed={dismissed} onRestore={handleRestore} onRestoreAll={handleRestoreAll} />
      )}
    </div>
  );
}
