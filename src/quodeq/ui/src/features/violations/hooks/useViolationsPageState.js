import { useEffect, useMemo, useRef, useState } from 'react';
import { readVisibleStandardIds, computeSummaryFromDimensions } from '../../../utils/visibleStandards.js';
import { readCachedState, writeCachedState, resetCachedScope } from '../../../utils/pageStateCache.js';
import { useDismissedFindings } from '../components/useDismissedFindings.js';

// Fresh tab click (tabKey changed) drops the cached file-tree path so the
// user lands at the root, then re-reads the (possibly just-reset) cache and
// fires the mount/round-trip refresh. Extracted from ViolationsPage.jsx
// verbatim.
export function useViolationsTabKeyReset({ tabKey, selectedProject, onRefresh }) {
  // Round-tripping through a file detail does NOT change tabKey, so the
  // cache survives unmount and the tree resumes where it was.
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

  return cached;
}

/**
 * ViolationsPage.jsx's dismissed-findings + file-tree-path + derived-summary
 * state. Extracted verbatim.
 */
export function useViolationsData({ accumulatedDimensions, selectedProject, onRefresh, onReconcile, initialFilePath, dismissRefreshKey, selectedSource }) {
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

// Composes the two hooks above the way ViolationsPage.jsx's body used to
// inline them back to back: the tab-key-reset cache read feeds
// useViolationsData's initialFilePath.
export function useViolationsPageState({ tabKey, selectedProject, onRefresh, onReconcile, accumulatedDimensions, dismissRefreshKey, selectedSource }) {
  const cached = useViolationsTabKeyReset({ tabKey, selectedProject, onRefresh });
  return useViolationsData({
    accumulatedDimensions,
    selectedProject,
    onRefresh,
    onReconcile,
    initialFilePath: cached.fileCurrentPath,
    dismissRefreshKey,
    selectedSource,
  });
}
