import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { listDismissedFindings, restoreFinding, restoreAllFindings } from '../../../api/index.js';
import { readVisibleStandardIds, computeSummaryFromDimensions } from '../../../utils/visibleStandards.js';
import { readCachedState, writeCachedState, resetCachedScope } from '../../../utils/pageStateCache.js';
import { buildFileTree, treeNodeToFileObj, HeatGridView } from '../../map/viz/index.js';
import DimensionHeatGridView from './DimensionHeatGridView.jsx';
import DismissedSubTab from './DismissedSubTab.jsx';
import { TermHeader, SevBadge, FlagPill } from '../../../components/terminal/index.js';

const MAX_TREE_DEPTH = 64;

function findSubtree(root, path) {
  if (!path) return root;
  function walk(node, depth = 0) {
    if (depth > MAX_TREE_DEPTH) return null;
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
      <HeatGridView node={currentNode} onDrillDown={setCurrentPath} onFileClick={handleFileClick} onCellClick={handleCellClick} variant="flat" />
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

function useViolationsData({ accumulatedDimensions, selectedProject, onRefresh, initialSubTab, initialFilePath }) {
  const [activeSubTab, _setActiveSubTab] = useState(initialSubTab);
  const setActiveSubTab = (v) => {
    writeCachedState('violations', selectedProject, { activeSubTab: v });
    _setActiveSubTab(v);
  };
  const [fileCurrentPath, _setFileCurrentPath] = useState(initialFilePath);
  const setFileCurrentPath = (v) => {
    writeCachedState('violations', selectedProject, { fileCurrentPath: v });
    _setFileCurrentPath(v);
  };

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

function SevInline({ severity }) {
  const sev = severity || {};
  if (!(sev.critical || sev.major || sev.minor)) return null;
  return (
    <span className="violations-sev-row">
      {sev.critical > 0 && <SevBadge level="critical" count={sev.critical} />}
      {sev.major > 0    && <SevBadge level="major" count={sev.major} />}
      {sev.minor > 0    && <SevBadge level="minor" count={sev.minor} />}
    </span>
  );
}

function ViolationsSubTabContent(props) {
  const { activeSubTab, visibleDimensions, dismissed, callbacks, fileCurrentPath, setFileCurrentPath, handleRestore, handleRestoreAll } = props;
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
  const { accumulatedDimensions, selectedProject } = data;
  const { onRefresh } = callbacks;

  // Fresh tab click (tabKey changed) drops the cached navigation state so
  // the user lands at the default sub-tab / root path. Round-tripping
  // through a file detail does NOT change tabKey, so the cache survives
  // unmount and the page resumes where it was.
  const lastTabKeyRef = useRef(tabKey);
  if (lastTabKeyRef.current !== tabKey) {
    resetCachedScope('violations', selectedProject);
    lastTabKeyRef.current = tabKey;
  }

  const cached = readCachedState('violations', selectedProject, {
    activeSubTab: 'dimension',
    fileCurrentPath: '',
  });

  useEffect(() => {
    onRefresh?.();
  }, [tabKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const {
    activeSubTab, setActiveSubTab, dismissed,
    handleRestore, handleRestoreAll, restoreError, visibleDimensions,
    summary, topFilesCount, uniquePrinciples,
    fileCurrentPath, setFileCurrentPath,
  } = useViolationsData({
    accumulatedDimensions,
    selectedProject,
    onRefresh,
    initialSubTab: cached.activeSubTab,
    initialFilePath: cached.fileCurrentPath,
  });

  const total = summary.totalViolations || 0;
  const subParts = [
    `${total} total`,
    `${visibleDimensions.length} dim${visibleDimensions.length !== 1 ? 's' : ''}`,
    `${uniquePrinciples} princ.`,
    `${topFilesCount} files`,
  ];
  const subLine = (
    <span className="violations-sub">
      <span className="violations-sub__text">{subParts.join(' · ')}</span>
      <SevInline severity={summary.severity} />
    </span>
  );

  return (
    <div className="violations-page violations-page--terminal">
      {restoreError && <div className="error-banner">{restoreError}</div>}
      <div className="violations-page__top">
        <TermHeader name="violations" sub={subLine} />
        <div className="violations-flag-row">
          <FlagPill flag="by-dimension" active={activeSubTab === 'dimension'} onClick={() => setActiveSubTab('dimension')} />
          <FlagPill flag="by-file"      active={activeSubTab === 'file'}      onClick={() => setActiveSubTab('file')} />
          <FlagPill flag="dismissed"    active={activeSubTab === 'dismissed'} count={dismissed.length || undefined} onClick={() => setActiveSubTab('dismissed')} />
        </div>
      </div>
      <ViolationsSubTabContent
        activeSubTab={activeSubTab} visibleDimensions={visibleDimensions} dismissed={dismissed}
        callbacks={callbacks} fileCurrentPath={fileCurrentPath} setFileCurrentPath={setFileCurrentPath}
        handleRestore={handleRestore} handleRestoreAll={handleRestoreAll}
      />
    </div>
  );
}
