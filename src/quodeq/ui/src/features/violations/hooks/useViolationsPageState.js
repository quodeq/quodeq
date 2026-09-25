import { useEffect, useMemo, useRef, useState } from 'react';
import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';
import { computeSummaryFromDimensions } from '../../../utils/visibleStandardsSummary.js';
import { readCachedState, writeCachedState, resetCachedScope } from '../../../utils/pageStateCache.js';
import { useDismissedFindings } from '../components/useDismissedFindings.js';

// This page's pageStateCache scope key.
const PAGE_STATE_SCOPE = 'violations';

/**
 * Fresh tab click (tabKey changed) drops the cached file-tree path so the
 * user lands at the root, then re-reads the (possibly just-reset) cache and
 * fires the mount/round-trip refresh.
 *
 * `cache` is an optional injected page-state cache (see pageStateCache.js);
 * with none given this goes through the module's own free functions (the
 * shared default).
 */
export function useViolationsTabKeyReset({ tabKey, selectedProject, onRefresh, cache }) {
  // Round-tripping through a file detail does NOT change tabKey, so the
  // cache survives unmount and the tree resumes where it was.
  const lastTabKeyRef = useRef(tabKey);
  const reset = cache ? cache.resetCachedScope : resetCachedScope;
  const read = cache ? cache.readCachedState : readCachedState;
  if (lastTabKeyRef.current !== tabKey) {
    reset(PAGE_STATE_SCOPE, selectedProject);
    lastTabKeyRef.current = tabKey;
  }

  const cached = read(PAGE_STATE_SCOPE, selectedProject, {
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
 * The Violations page's dismissed-findings, file-tree path and derived
 * summary state: the visible dimensions, their rolled-up counts, and the
 * currently browsed path (cached per project so a round trip resumes there).
 */
export function useViolationsData({ accumulatedDimensions, selectedProject, onReconcile, initialFilePath, dismissRefreshKey, selectedSource, cache }) {
  const [fileCurrentPath, _setFileCurrentPath] = useState(initialFilePath);
  const write = cache ? cache.writeCachedState : writeCachedState;
  const setFileCurrentPath = (v) => {
    write(PAGE_STATE_SCOPE, selectedProject, { fileCurrentPath: v });
    _setFileCurrentPath(v);
  };

  const [restoreError, setRestoreError] = useState(null);
  // dismissRefreshKey is bumped by App.jsx after a dismiss POST elsewhere.
  // useDismissedFindings refetches when this changes, so the dismissed
  // sub-tab reflects new entries without needing the user to re-open the
  // page or switch projects.
  const { dismissed, handleRestore, handleRestoreAll, handleDelete, handleDeleteAll } =
    useDismissedFindings({ selectedProject, setRestoreError, refreshKey: dismissRefreshKey, selectedSource, onReconcile });

  const visibleDimensions = useMemo(() => {
    const visibleSet = new Set(readVisibleStandardIds());
    return accumulatedDimensions.filter((d) => visibleSet.has((d.dimension || '').toLowerCase()));
  }, [accumulatedDimensions]);

  const summary = useMemo(() => computeSummaryFromDimensions(visibleDimensions), [visibleDimensions]);

  const topFilesCount = useMemo(
    () => countDistinctViolationField(visibleDimensions, 'file'),
    [visibleDimensions]
  );

  const uniquePrinciples = useMemo(
    () => countDistinctViolationField(visibleDimensions, 'principle'),
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

/**
 * How many distinct values of `field` the visible dimensions' violations
 * carry. Missing values are dropped rather than counted as one empty group.
 *
 * @param {Array} dimensions
 * @param {string} field Violation field to count distinct values of.
 * @returns {number}
 */
function countDistinctViolationField(dimensions, field) {
  const values = dimensions.flatMap((d) => (d.violations || []).map((v) => v[field]));
  return new Set(values.filter(Boolean)).size;
}

/**
 * The Violations page's whole state in one call: the tab-key reset runs
 * first, and the cached path it reads back seeds useViolationsData's
 * initialFilePath. Order matters, which is why they are composed here rather
 * than called side by side at the page. `cache` is an optional injected
 * page-state cache; omit it in production, where the page shares the
 * module-level default (see pageStateCache.js).
 */
export function useViolationsPageState({ tabKey, selectedProject, onRefresh, onReconcile, accumulatedDimensions, dismissRefreshKey, selectedSource, cache }) {
  const cached = useViolationsTabKeyReset({ tabKey, selectedProject, onRefresh, cache });
  return useViolationsData({
    accumulatedDimensions,
    selectedProject,
    onReconcile,
    initialFilePath: cached.fileCurrentPath,
    dismissRefreshKey,
    selectedSource,
    cache,
  });
}
