import { useCallback, useMemo } from 'react';
import { buildFileTree, treeNodeToFileObj, HeatGridView } from '../../map/viz/index.js';
import DimensionHeatGridView from './DimensionHeatGridView.jsx';
import DismissedSubTab from './DismissedSubTab.jsx';
import { TermHeader, SevBadge, FlagPill } from '../../../components/terminal/index.js';
import { renderViolationsEmptyState } from './ViolationsEmptyStates.jsx';
import { useViolationsPageState } from '../hooks/useViolationsPageState.js';
import SharedReadOnlyBadge from '../../../components/SharedReadOnlyBadge.jsx';
import { t } from '../../../strings/index.js';
import { walkTree } from '../../../utils/treeWalk.js';
import { PROJECT_SOURCE } from '../../../vocab/projectSource.js';
import { VIOLATIONS_SUB_TAB } from '../violationsVocab.js';
import { pluralKey } from '../../../utils/plural.js';

function findSubtree(root, path) {
  if (!path) return root;
  return walkTree(root, (node) => node.path === path) || root;
}

// findParentPath and buildBreadcrumbPath are exported for
// ViolationsPage.treeWalk.test.jsx.
export function findParentPath(root, currentPath) {
  let parentPath = '';
  walkTree(root, (node, ancestors) => {
    if (node.path !== currentPath) return false;
    parentPath = ancestors.length > 0 ? ancestors[ancestors.length - 1].path : '';
    return true;
  });
  return parentPath;
}

export function buildBreadcrumbPath(root, path) {
  if (!path) return [];
  let segments = [];
  walkTree(root, (node, ancestors) => {
    if (node.path !== path) return false;
    segments = [...ancestors, node].map((n) => ({ name: n.name, path: n.path }));
    return true;
  });
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
    t(pluralKey(visibleDimensions.length, 'violations.subDim', 'violations.subDims'), { count: visibleDimensions.length }),
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
        badge={selectedSource === PROJECT_SOURCE.SHARED ? <SharedReadOnlyBadge /> : null}
      />
      <div className="violations-flag-row">
        <FlagPill flag={t('violations.flagByDimension')} active={activeSubTab === VIOLATIONS_SUB_TAB.DIMENSION} onClick={() => setActiveSubTab(VIOLATIONS_SUB_TAB.DIMENSION)} />
        <FlagPill flag={t('violations.flagByFile')}      active={activeSubTab === VIOLATIONS_SUB_TAB.FILE}      onClick={() => setActiveSubTab(VIOLATIONS_SUB_TAB.FILE)} />
        <FlagPill flag={t('violations.flagDismissed')}   active={activeSubTab === VIOLATIONS_SUB_TAB.DISMISSED} count={dismissed.length || undefined} onClick={() => setActiveSubTab(VIOLATIONS_SUB_TAB.DISMISSED)} />
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
  if (activeSubTab === VIOLATIONS_SUB_TAB.FILE) {
    return <FileSubTab dimensions={visibleDimensions} onFileClick={callbacks.onFileClick} currentPath={fileCurrentPath} setCurrentPath={setFileCurrentPath} />;
  }
  if (activeSubTab === VIOLATIONS_SUB_TAB.DIMENSION) {
    return <DimensionHeatGridView dimensions={visibleDimensions} onDimensionClick={callbacks.onDimensionClick} onPrincipleClick={callbacks.onPrincipleClick} onCellClick={callbacks.onCellClick} />;
  }
  if (activeSubTab === VIOLATIONS_SUB_TAB.DISMISSED) {
    // Shared projects have no mutation route on the backend — pass undefined
    // instead of the real handlers so DismissedSubTab hides the actions and
    // the list stays visible read-only. useDismissedFindings' own handlers
    // also no-op as defense in depth (see that hook), but the button must not
    // even render here.
    const actions = selectedSource === PROJECT_SOURCE.SHARED
      ? {}
      : { onRestore: handleRestore, onRestoreAll: handleRestoreAll, onDelete: handleDelete, onDeleteAll: handleDeleteAll };
    return dismissed.length > 0
      ? <DismissedSubTab dismissed={dismissed} {...actions} />
      : <p className="empty-state">{t('violations.noDismissedViolations')}</p>;
  }
  return null;
}

export default function ViolationsPage({ data, callbacks, tabKey = 0, subTab = VIOLATIONS_SUB_TAB.DIMENSION, onSubTabChange }) {
  const { accumulatedDimensions = [], selectedProject, dismissRefreshKey = 0, selectedSource = PROJECT_SOURCE.LOCAL } = data;
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
      {restoreError && <div className="error-banner" role="alert">{restoreError}</div>}
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
