import { useCallback, useEffect, useMemo, useState } from 'react';
import { listDismissedFindings, restoreFinding, restoreAllFindings } from '../../../api/index.js';
import { readVisibleStandardIds, computeSummaryFromDimensions } from '../../../utils/visibleStandards.js';
import { complianceRatio } from '../../../utils/formatters.js';
import { buildFileTree, treeNodeToFileObj } from '../../map/utils/fileTree.js';
import HeatGridView from '../../map/components/HeatGridView.jsx';
import DimensionHeatGridView from './DimensionHeatGridView.jsx';
import DismissedSubTab from './DismissedSubTab.jsx';


function findSubtree(root, path) {
  if (!path) return root;
  function walk(node) {
    if (node.path === path) return node;
    for (const child of node.children) {
      const found = walk(child);
      if (found) return found;
    }
    return null;
  }
  return walk(root) || root;
}

function findParentPath(root, currentPath) {
  function walk(node, parentPath) {
    if (node.path === currentPath) return parentPath;
    for (const child of node.children) {
      const found = walk(child, node.path);
      if (found !== null) return found;
    }
    return null;
  }
  return walk(root, '') || '';
}

function buildBreadcrumbPath(root, path) {
  if (!path) return [];
  const segments = [];
  function walk(node) {
    if (node.path === path) { segments.push({ name: node.name, path: node.path }); return true; }
    for (const child of node.children) {
      if (walk(child)) { segments.unshift({ name: node.name, path: node.path }); return true; }
    }
    return false;
  }
  walk(root);
  return segments.filter((s) => s.path);
}

function FileBreadcrumb({ path, onNavigate, onBack }) {
  if (path.length === 0) return null;
  const segments = [{ name: 'Root', path: '' }, ...path];
  return (
    <div className="map-breadcrumb">
      <button type="button" className="map-breadcrumb-back" onClick={onBack} title="Go back">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6" /></svg>
      </button>
      {segments.map((seg, i) => (
        <span key={seg.path}>
          {i > 0 && <span className="map-breadcrumb-sep">&rsaquo;</span>}
          {i < segments.length - 1 ? (
            <button type="button" className="map-breadcrumb-seg" onClick={() => onNavigate(seg.path)}>{seg.name}</button>
          ) : (
            <span className="map-breadcrumb-current">{seg.name}</span>
          )}
        </span>
      ))}
    </div>
  );
}

function FileSubTab({ dimensions, onFileClick, currentPath, setCurrentPath }) {
  const fullTree = useMemo(() => buildFileTree(dimensions), [dimensions]);
  const currentNode = useMemo(() => findSubtree(fullTree, currentPath), [fullTree, currentPath]);
  const breadcrumb = useMemo(() => buildBreadcrumbPath(fullTree, currentPath), [fullTree, currentPath]);

  const handleFileClick = useCallback((treeNode) => {
    if (treeNode.isFile) onFileClick?.(treeNodeToFileObj(treeNode));
  }, [onFileClick]);

  const handleCellClick = useCallback(({ row, severity }) => {
    // Navigate to file/folder detail filtered by severity
    onFileClick?.(treeNodeToFileObj(row, { severity: severity || undefined }));
  }, [onFileClick]);

  return (
    <>
      <FileBreadcrumb path={breadcrumb} onNavigate={setCurrentPath} onBack={() => setCurrentPath(findParentPath(fullTree, currentPath))} />
      <HeatGridView node={currentNode} onDrillDown={setCurrentPath} onFileClick={handleFileClick} onCellClick={handleCellClick} />
    </>
  );
}

let _savedSubTab = 'dimension';
let _savedFilePath = '';

function useViolationsData({ accumulatedDimensions, selectedProject, onRefresh }) {
  const [activeSubTab, _setActiveSubTab] = useState(_savedSubTab);
  const setActiveSubTab = (v) => { _savedSubTab = v; _setActiveSubTab(v); };
  const [dismissed, setDismissed] = useState([]);
  const [fileCurrentPath, _setFileCurrentPath] = useState(_savedFilePath);
  const setFileCurrentPath = (v) => { _savedFilePath = v; _setFileCurrentPath(v); };

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

  const summary = useMemo(() => computeSummaryFromDimensions(visibleDimensions), [visibleDimensions]);

  const topFilesCount = useMemo(
    () => new Set(visibleDimensions.flatMap((d) => (d.violations || []).map((v) => v.file)).filter(Boolean)).size,
    [visibleDimensions]
  );

  const uniquePrinciples = useMemo(
    () => new Set(visibleDimensions.flatMap((d) => (d.violations || []).map((v) => v.principle)).filter(Boolean)).size,
    [visibleDimensions]
  );

  return {
    activeSubTab, setActiveSubTab, dismissed,
    handleRestore, handleRestoreAll, visibleDimensions,
    summary, topFilesCount, uniquePrinciples,
    fileCurrentPath, setFileCurrentPath,
  };
}

let _lastViolationsTabKey = null;

export default function ViolationsPage({ data, callbacks, isDirectNav, tabKey = 0 }) {
  const isFreshTabClick = _lastViolationsTabKey !== null && tabKey !== _lastViolationsTabKey;
  _lastViolationsTabKey = tabKey;
  if (isFreshTabClick) _savedFilePath = '';

  const { accumulatedDimensions, selectedProject } = data;
  const { onDimensionClick, onFileClick, onPrincipleClick, onRefresh } = callbacks;

  // Refresh data on mount (ensures fresh data after returning from detail pages) and on tab re-click
  useEffect(() => {
    onRefresh?.();
  }, [tabKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const {
    activeSubTab, setActiveSubTab, dismissed,
    handleRestore, handleRestoreAll, visibleDimensions,
    summary, topFilesCount, uniquePrinciples,
    fileCurrentPath, setFileCurrentPath,
  } = useViolationsData({ accumulatedDimensions, selectedProject, onRefresh });

  return (
    <div className="violations-page">
      <div className="map-header">
        <h2 className="page-title">Violations</h2>
        <div className="map-pill-group">
          {[
            { id: 'dimension', label: 'By Dimension' },
            { id: 'file', label: 'By File' },
            { id: 'dismissed', label: dismissed.length > 0 ? `Dismissed (${dismissed.length})` : 'Dismissed' },
          ].map((tab) => (
            <button key={tab.id} type="button" className={`map-pill${activeSubTab === tab.id ? ' active' : ''}`} onClick={() => setActiveSubTab(tab.id)}>
              {tab.label}
            </button>
          ))}
        </div>
      </div>
      <section className="panel violations-stats-panel">
        <div className="violations-stats-grid">
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Violations</span>
            <span className="acc-eval-stat-value">{summary.totalViolations || 0}</span>
            <div className="acc-eval-tags">
              {(summary.severity?.critical || 0) > 0 && <span className="severity-tag critical">{summary.severity.critical} critical</span>}
              {(summary.severity?.major || 0) > 0 && <span className="severity-tag major">{summary.severity.major} major</span>}
              {(summary.severity?.minor || 0) > 0 && <span className="severity-tag minor">{summary.severity.minor} minor</span>}
            </div>
          </div>
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Compliance</span>
            <span className="acc-eval-stat-value">{summary.totalCompliance || 0}</span>
          </div>
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Ratio</span>
            <span className="acc-eval-stat-value">{complianceRatio(summary.totalViolations || 0, summary.totalCompliance || 0)}</span>
          </div>
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Files</span>
            <span className="acc-eval-stat-value">{topFilesCount}</span>
          </div>
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Principles</span>
            <span className="acc-eval-stat-value">{uniquePrinciples}</span>
          </div>
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Dimensions</span>
            <span className="acc-eval-stat-value">{visibleDimensions.length}</span>
          </div>
        </div>
      </section>
      {activeSubTab === 'file' && (
        <FileSubTab dimensions={visibleDimensions} onFileClick={onFileClick} currentPath={fileCurrentPath} setCurrentPath={setFileCurrentPath} />
      )}
      {activeSubTab === 'dimension' && (
        <DimensionHeatGridView dimensions={visibleDimensions} onDimensionClick={onDimensionClick} onPrincipleClick={onPrincipleClick} onCellClick={callbacks.onCellClick} />
      )}
      {activeSubTab === 'dismissed' && (
        dismissed.length > 0
          ? <DismissedSubTab dismissed={dismissed} onRestore={handleRestore} onRestoreAll={handleRestoreAll} />
          : <p className="empty-state">No dismissed violations.</p>
      )}
    </div>
  );
}
