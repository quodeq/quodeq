import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { readVisibleStandardIds, computeSummaryFromDimensions } from '../../../utils/visibleStandards.js';
import { readCachedState, writeCachedState, resetCachedScope } from '../../../utils/pageStateCache.js';
import { buildFileTree, treeNodeToFileObj, HeatGridView } from '../../map/viz/index.js';
import DimensionHeatGridView from './DimensionHeatGridView.jsx';
import DismissedSubTab from './DismissedSubTab.jsx';
import { TermHeader, SevBadge, FlagPill } from '../../../components/terminal/index.js';
import { useDismissedFindings } from './useDismissedFindings.js';
import EmptyState from '../../../components/EmptyState.jsx';
import LoadingScreen from '../../../components/LoadingScreen.jsx';

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
    // Pass the full file object and let FileDetailPage apply the filter, so
    // the severity-filter pill reflects the user's choice (rather than the
    // file silently arriving pre-filtered).
    onFileClick?.(treeNodeToFileObj(row), { severity: severity || undefined });
  }, [onFileClick]);

  return (
    <>
      <FileBreadcrumb path={breadcrumb} onNavigate={setCurrentPath} onBack={() => setCurrentPath(findParentPath(fullTree, currentPath))} />
      <HeatGridView node={currentNode} onDrillDown={setCurrentPath} onFileClick={handleFileClick} onCellClick={handleCellClick} variant="flat" />
    </>
  );
}

function useViolationsData({ accumulatedDimensions, selectedProject, onRefresh, initialSubTab, initialFilePath, dismissRefreshKey, selectedSource }) {
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
  // dismissRefreshKey is bumped by App.jsx after a dismiss POST elsewhere.
  // useDismissedFindings refetches when this changes, so the dismissed
  // sub-tab reflects new entries without needing the user to re-open the
  // page or switch projects.
  const { dismissed, handleRestore, handleRestoreAll, handleDelete, handleDeleteAll } =
    useDismissedFindings(selectedProject, onRefresh, setRestoreError, dismissRefreshKey, selectedSource);

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
    handleRestore, handleRestoreAll, handleDelete, handleDeleteAll,
    restoreError, visibleDimensions,
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

export function ViolationsSubTabContent(props) {
  const {
    activeSubTab, visibleDimensions, dismissed, callbacks,
    fileCurrentPath, setFileCurrentPath,
    handleRestore, handleRestoreAll, handleDelete, handleDeleteAll,
    selectedSource,
  } = props;
  if (activeSubTab === 'file') {
    return <FileSubTab dimensions={visibleDimensions} onFileClick={callbacks.onFileClick} currentPath={fileCurrentPath} setCurrentPath={setFileCurrentPath} />;
  }
  if (activeSubTab === 'dimension') {
    return <DimensionHeatGridView dimensions={visibleDimensions} onDimensionClick={callbacks.onDimensionClick} onPrincipleClick={callbacks.onPrincipleClick} onCellClick={callbacks.onCellClick} />;
  }
  if (activeSubTab === 'dismissed') {
    // Shared projects have no mutation route on the backend — pass undefined
    // instead of the real handlers so DismissedSubTab hides the actions and
    // the list stays visible read-only. useDismissedFindings' own handlers
    // also no-op as defense in depth (see that hook), but the button must not
    // even render here.
    const isShared = selectedSource === 'shared';
    return dismissed.length > 0
      ? (
        <DismissedSubTab
          dismissed={dismissed}
          onRestore={isShared ? undefined : handleRestore}
          onRestoreAll={isShared ? undefined : handleRestoreAll}
          onDelete={isShared ? undefined : handleDelete}
          onDeleteAll={isShared ? undefined : handleDeleteAll}
        />
      )
      : <p className="empty-state">No dismissed violations.</p>;
  }
  return null;
}

export default function ViolationsPage({ data, callbacks, isDirectNav, tabKey = 0 }) {
  const { accumulatedDimensions = [], selectedProject, dismissRefreshKey = 0, selectedSource = 'local' } = data;
  const { projects = [], projectsLoaded, projectName, loading, isFetching } = data;
  const { onNavigate, onRefresh } = callbacks;

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
    handleRestore, handleRestoreAll, handleDelete, handleDeleteAll,
    restoreError, visibleDimensions,
    summary, topFilesCount, uniquePrinciples,
    fileCurrentPath, setFileCurrentPath,
  } = useViolationsData({
    accumulatedDimensions,
    selectedProject,
    onRefresh,
    initialSubTab: cached.activeSubTab,
    initialFilePath: cached.fileCurrentPath,
    dismissRefreshKey,
    selectedSource,
  });

  if (!projectsLoaded) return <LoadingScreen />;
  if (projects.length === 0) {
    return (
      <div className="violations-page violations-page--terminal">
        <TermHeader name="violations" sub="no projects yet" />
        <EmptyState
          title="No projects yet"
          description="Add a project to start analyzing code quality."
          actionLabel="Add a project"
          onAction={() => onNavigate?.('projects')}
        />
      </div>
    );
  }
  if (!selectedProject) {
    return (
      <div className="violations-page violations-page--terminal">
        <TermHeader name="violations" sub="no project selected" />
        <EmptyState
          title="No project selected"
          description="Pick a project to view its violations."
          actionLabel="Choose project"
          onAction={() => onNavigate?.('projects')}
        />
      </div>
    );
  }
  const hasAnyDimensionData = (accumulatedDimensions || []).length > 0;
  if (!hasAnyDimensionData) {
    if (loading || isFetching) return <LoadingScreen />;
    return (
      <div className="violations-page violations-page--terminal">
        <TermHeader name="violations" sub="no evaluations yet" />
        <EmptyState
          title="No evaluations yet"
          description={`Run an evaluation for ${projectName || selectedProject} to populate this page.`}
          actionLabel="Start evaluation"
          onAction={() => onNavigate?.('evaluate')}
        />
      </div>
    );
  }

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
        handleDelete={handleDelete} handleDeleteAll={handleDeleteAll}
        selectedSource={selectedSource}
      />
    </div>
  );
}
