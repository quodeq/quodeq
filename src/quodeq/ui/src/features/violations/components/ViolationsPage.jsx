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
import ViolationsSkeleton from './ViolationsSkeleton.jsx';
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

function useViolationsData({ accumulatedDimensions, selectedProject, onRefresh, onReconcile, initialFilePath, dismissRefreshKey, selectedSource }) {
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
    useDismissedFindings(selectedProject, onRefresh, setRestoreError, dismissRefreshKey, selectedSource, onReconcile);

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
    dismissed,
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

  // Fresh tab click (tabKey changed) drops the cached file-tree path so the
  // user lands at the root. Round-tripping through a file detail does NOT
  // change tabKey, so the cache survives unmount and the tree resumes where
  // it was.
  const lastTabKeyRef = useRef(tabKey);
  if (lastTabKeyRef.current !== tabKey) {
    resetCachedScope('violations', selectedProject);
    lastTabKeyRef.current = tabKey;
  }

  const cached = readCachedState('violations', selectedProject, {
    fileCurrentPath: '',
  });

  // Fires on every mount, including plain drill-down/back navigation with no
  // mutation involved (the page remounts on every round trip) -- onRefresh
  // MUST stay the lazy refreshDashboard (mark-stale only). Do not wire this
  // to an active-refetching callback (e.g. scheduleDashboardReconcile); that
  // turns routine navigation into a forced re-download of the dashboard
  // payload. See App.jsx's ViolationsRoute for the onRefresh/onReconcile split.
  useEffect(() => {
    onRefresh?.();
  }, [tabKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const {
    dismissed,
    handleRestore, handleRestoreAll, handleDelete, handleDeleteAll,
    restoreError, visibleDimensions,
    summary, topFilesCount, uniquePrinciples,
    fileCurrentPath, setFileCurrentPath,
  } = useViolationsData({
    accumulatedDimensions,
    selectedProject,
    onRefresh,
    onReconcile,
    initialFilePath: cached.fileCurrentPath,
    dismissRefreshKey,
    selectedSource,
  });

  if (!projectsLoaded) return <LoadingScreen />;
  // The LOCAL projects list can legitimately be empty while a teammate is
  // viewing a shared project (they may have never added a local project of
  // their own) -- gate this wall on the local list only for local selections,
  // so a shared selection falls through to the normal shared data flow below.
  if (projects.length === 0 && selectedSource !== 'shared') {
    return (
      <div className="violations-page violations-page--terminal">
        <TermHeader name={t('violations.termName')} sub={t('violations.subNoProjects')} />
        <EmptyState
          title={t('overview.noProjectsTitle')}
          description={t('overview.noProjectsDesc')}
          actionLabel={t('overview.addProject')}
          onAction={() => onNavigate?.('projects')}
        />
      </div>
    );
  }
  if (!selectedProject) {
    return (
      <div className="violations-page violations-page--terminal">
        <TermHeader name={t('violations.termName')} sub={t('violations.subNoProjectSelected')} />
        <EmptyState
          title={t('overview.noProjectSelectedTitle')}
          description={t('violations.noProjectSelectedDesc')}
          actionLabel={t('overview.chooseProject')}
          onAction={() => onNavigate?.('projects')}
        />
      </div>
    );
  }
  const hasAnyDimensionData = (accumulatedDimensions || []).length > 0;
  const isRefreshing = isFetching && !loading;
  if (!hasAnyDimensionData) {
    if (loading) {
      return (
        <div className="violations-page violations-page--terminal">
          <TermHeader name={t('violations.termName')} sub={t('overview.loading')} />
          <ViolationsSkeleton />
        </div>
      );
    }
    // A failed fetch with nothing to show must render as an error, not the
    // "no evaluations yet" empty state -- otherwise a 404/500/timeout tells
    // the user their existing evaluations are gone. While a retry is in
    // flight (error still set, isFetching true), show the loader instead so
    // clicking Retry visibly does something.
    if (error) {
      if (isFetching) {
        return (
          <div className="violations-page violations-page--terminal">
            <TermHeader name={t('violations.termName')} sub={t('overview.loading')} />
            <ViolationsSkeleton />
          </div>
        );
      }
      return (
        <div className="violations-page violations-page--terminal">
          <TermHeader name={t('violations.termName')} sub={t('violations.subError')} />
          <EmptyState
            title={t('overview.loadProjectFailedTitle')}
            description={error}
            actionLabel={t('overview.retry')}
            onAction={() => onRetry?.()}
          />
        </div>
      );
    }
    // Shared projects are read-only in the app -- evaluations only ever run
    // locally, so "Start evaluation" has nowhere useful to send a
    // shared-project viewer (see DashboardPage's NoCompletedEvalPanel, the
    // precedent this mirrors).
    if (selectedSource === 'shared') {
      return (
        <div className={`violations-page violations-page--terminal${isRefreshing ? ' dashboard-refreshing' : ''}`}>
          <TermHeader name={t('violations.termName')} sub={t('violations.subNoEvals')} />
          <EmptyState
            title={t('overview.noCompletedEvalTitle')}
            description={t('overview.noCompletedEvalSharedDesc')}
          />
        </div>
      );
    }
    return (
      <div className={`violations-page violations-page--terminal${isRefreshing ? ' dashboard-refreshing' : ''}`}>
        <TermHeader name={t('violations.termName')} sub={t('violations.subNoEvals')} />
        <EmptyState
          title={t('overview.noEvalsTitle')}
          description={t('overview.noEvalsDesc', { name: projectName || selectedProject })}
          actionLabel={t('overview.startEvaluation')}
          onAction={() => onNavigate?.('evaluate')}
        />
      </div>
    );
  }

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
    <div className={`violations-page violations-page--terminal${isRefreshing ? ' dashboard-refreshing' : ''}`}>
      {restoreError && <div className="error-banner">{restoreError}</div>}
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
