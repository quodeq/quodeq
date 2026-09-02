import { useCallback, useMemo } from 'react';
import { buildFileTree, treeNodeToFileObj, HeatGridView } from '../../map/viz/index.js';
import DimensionHeatGridView from './DimensionHeatGridView.jsx';
import DismissedSubTab from './DismissedSubTab.jsx';
import { TermHeader, SevBadge, FlagPill } from '../../../components/terminal/index.js';
import { renderViolationsEmptyState } from './ViolationsEmptyStates.jsx';
import { useViolationsPageState } from '../hooks/useViolationsPageState.js';
import SharedReadOnlyBadge from '../../../components/SharedReadOnlyBadge.jsx';
import { t } from '../../../strings/index.js';

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
  const segments = [{ name: t('violations.rootCrumb'), path: '' }, ...path];
  return (
    <div className="map-breadcrumb">
      <button type="button" className="map-breadcrumb-back" onClick={onBack} title={t('violations.goBackTitle')}>
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

function ViolationsHeader({ summary, visibleDimensions, topFilesCount, uniquePrinciples, selectedSource, activeSubTab, setActiveSubTab, dismissed }) {
  const total = summary.totalViolations || 0;
  const subParts = [
    t('violations.subTotal', { count: total }),
    visibleDimensions.length === 1
      ? t('violations.subDim', { count: visibleDimensions.length })
      : t('violations.subDims', { count: visibleDimensions.length }),
    t('violations.subPrinciples', { count: uniquePrinciples }),
    t('violations.subFiles', { count: topFilesCount }),
  ];
  const subLine = (
    <span className="violations-sub">
      <span className="violations-sub__text">{subParts.join(' · ')}</span>
      <SevInline severity={summary.severity} />
    </span>
  );
  return (
    <div className="violations-page__top">
      <TermHeader
        name={t('violations.termName')}
        sub={subLine}
        badge={selectedSource === 'shared' ? <SharedReadOnlyBadge /> : null}
      />
      <div className="violations-flag-row">
        <FlagPill flag={t('violations.flagByDimension')} active={activeSubTab === 'dimension'} onClick={() => setActiveSubTab('dimension')} />
        <FlagPill flag={t('violations.flagByFile')}      active={activeSubTab === 'file'}      onClick={() => setActiveSubTab('file')} />
        <FlagPill flag={t('violations.flagDismissed')}   active={activeSubTab === 'dismissed'} count={dismissed.length || undefined} onClick={() => setActiveSubTab('dismissed')} />
      </div>
    </div>
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
      : <p className="empty-state">{t('violations.noDismissedViolations')}</p>;
  }
  return null;
}

export default function ViolationsPage({ data, callbacks, isDirectNav, tabKey = 0, subTab = 'dimension', onSubTabChange }) {
  const { accumulatedDimensions = [], selectedProject, dismissRefreshKey = 0, selectedSource = 'local' } = data;
  const { projects = [], projectsLoaded, projectName, loading, isFetching, error } = data;
  const { onNavigate, onRefresh, onReconcile, onRetry } = callbacks;

  // The active sub-tab lives in the nav-stack entry, not component state:
  // `subTab` arrives as a route param and flipping it replaces the entry in
  // place (see App.jsx's ViolationsRoute), so back/forward restore it while
  // history never grows per flip. A fresh tab click creates an entry with no
  // subTab param, which lands on the default just like the old cache reset.
  const activeSubTab = subTab;
  const setActiveSubTab = (v) => onSubTabChange?.(v);

  const {
    dismissed,
    handleRestore, handleRestoreAll, handleDelete, handleDeleteAll,
    restoreError, visibleDimensions,
    summary, topFilesCount, uniquePrinciples,
    fileCurrentPath, setFileCurrentPath,
  } = useViolationsPageState({ tabKey, selectedProject, onRefresh, onReconcile, accumulatedDimensions, dismissRefreshKey, selectedSource });

  const emptyState = renderViolationsEmptyState({
    projectsLoaded, projects, selectedSource, selectedProject, onNavigate,
    accumulatedDimensions, loading, isFetching, error, projectName, onRetry,
  });
  if (emptyState) return emptyState;
  const isRefreshing = isFetching && !loading;

  return (
    <div className={`violations-page violations-page--terminal${isRefreshing ? ' dashboard-refreshing' : ''}`}>
      {restoreError && <div className="error-banner">{restoreError}</div>}
      <ViolationsHeader
        summary={summary} visibleDimensions={visibleDimensions} topFilesCount={topFilesCount} uniquePrinciples={uniquePrinciples}
        selectedSource={selectedSource} activeSubTab={activeSubTab} setActiveSubTab={setActiveSubTab} dismissed={dismissed}
      />
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
