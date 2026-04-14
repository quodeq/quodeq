import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { listDismissedFindings, restoreFinding, restoreAllFindings } from '../../../api/index.js';
import { readVisibleStandardIds, computeSummaryFromDimensions } from '../../../utils/visibleStandards.js';
import { complianceRatio } from '../../../utils/formatters.js';
import { buildFileTree, treeNodeToFileObj, HeatGridView } from '../../map/viz/index.js';
import DimensionHeatGridView from './DimensionHeatGridView.jsx';
import DismissedSubTab from './DismissedSubTab.jsx';


function findSubtree(root, path) {
  if (!path) return root;
  function walk(node, depth = 0) {
    if (depth > 64) return null;
    if (node.path === path) return node;
    for (const child of node.children) {
      const found = walk(child, depth + 1);
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

function useDismissedFindings(selectedProject, onRefresh, setRestoreError) {
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
      setRestoreError?.('Failed to restore finding. Please try again.');
    }
  }, [selectedProject, onRefresh, setRestoreError]);

  const handleRestoreAll = useCallback(async () => {
    try {
      await restoreAllFindings(selectedProject);
      setDismissed([]);
      onRefresh?.();
    } catch (err) {
      console.error('Failed to restore all findings:', err);
      setRestoreError?.('Failed to restore all findings. Please try again.');
    }
  }, [selectedProject, onRefresh, setRestoreError]);

  return { dismissed, handleRestore, handleRestoreAll };
}

function useViolationsData({ accumulatedDimensions, selectedProject, onRefresh, savedSubTabRef, savedFilePathRef }) {
  const [activeSubTab, _setActiveSubTab] = useState(savedSubTabRef.current);
  const setActiveSubTab = (v) => { savedSubTabRef.current = v; _setActiveSubTab(v); };
  const [fileCurrentPath, _setFileCurrentPath] = useState(savedFilePathRef.current);
  const setFileCurrentPath = (v) => { savedFilePathRef.current = v; _setFileCurrentPath(v); };

  const [restoreError, setRestoreError] = useState(null);
  const { dismissed, handleRestore, handleRestoreAll } = useDismissedFindings(selectedProject, onRefresh, setRestoreError);

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
    handleRestore, handleRestoreAll, restoreError, visibleDimensions,
    summary, topFilesCount, uniquePrinciples,
    fileCurrentPath, setFileCurrentPath,
  };
}

function ViolationsStatsGrid({ summary, topFilesCount, uniquePrinciples, dimensionCount }) {
  return (
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
          <span className="acc-eval-stat-value">{dimensionCount}</span>
        </div>
      </div>
    </section>
  );
}

function ViolationsSubTabContent({ activeSubTab, visibleDimensions, dismissed, callbacks, fileCurrentPath, setFileCurrentPath, handleRestore, handleRestoreAll }) {
  if (activeSubTab === 'file') {
    return <FileSubTab dimensions={visibleDimensions} onFileClick={callbacks.onFileClick} currentPath={fileCurrentPath} setCurrentPath={setFileCurrentPath} />;
  }
  if (activeSubTab === 'dimension') {
    return <DimensionHeatGridView dimensions={visibleDimensions} onDimensionClick={callbacks.onDimensionClick} onPrincipleClick={callbacks.onPrincipleClick} onCellClick={callbacks.onCellClick} />;
  }
  if (activeSubTab === 'dismissed') {
    return dismissed.length > 0
      ? <DismissedSubTab dismissed={dismissed} onRestore={handleRestore} onRestoreAll={handleRestoreAll} />
      : <p className="empty-state">No dismissed violations.</p>;
  }
  return null;
}

export default function ViolationsPage({ data, callbacks, isDirectNav, tabKey = 0 }) {
  const savedSubTabRef = useRef('dimension');
  const savedFilePathRef = useRef('');
  const lastViolationsTabKeyRef = useRef(null);

  const isFreshTabClick = lastViolationsTabKeyRef.current !== null && tabKey !== lastViolationsTabKeyRef.current;
  lastViolationsTabKeyRef.current = tabKey;
  if (isFreshTabClick) savedFilePathRef.current = '';

  const { accumulatedDimensions, selectedProject } = data;
  const { onRefresh } = callbacks;

  useEffect(() => {
    onRefresh?.();
  }, [tabKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const {
    activeSubTab, setActiveSubTab, dismissed,
    handleRestore, handleRestoreAll, restoreError, visibleDimensions,
    summary, topFilesCount, uniquePrinciples,
    fileCurrentPath, setFileCurrentPath,
  } = useViolationsData({ accumulatedDimensions, selectedProject, onRefresh, savedSubTabRef, savedFilePathRef });

  return (
    <div className="violations-page">
      {restoreError && <div className="error-banner">{restoreError}</div>}
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
      <ViolationsStatsGrid summary={summary} topFilesCount={topFilesCount} uniquePrinciples={uniquePrinciples} dimensionCount={visibleDimensions.length} />
      <ViolationsSubTabContent
        activeSubTab={activeSubTab} visibleDimensions={visibleDimensions} dismissed={dismissed}
        callbacks={callbacks} fileCurrentPath={fileCurrentPath} setFileCurrentPath={setFileCurrentPath}
        handleRestore={handleRestore} handleRestoreAll={handleRestoreAll}
      />
    </div>
  );
}
