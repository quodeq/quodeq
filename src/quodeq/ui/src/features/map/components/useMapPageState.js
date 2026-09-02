import { useRef, useEffect } from 'react';
import { treeNodeToFileObj } from '../viz/index.js';
import { readCachedState, resetCachedScope } from '../../../utils/pageStateCache.js';
import { useDashboardFullHeight } from './useDashboardFullHeight.js';
import { useVisibleStandards } from './useVisibleStandards.js';
import { useMapDisplayPrefs } from './useMapDisplayPrefs.js';
import { useMapDimensionFilter } from './useMapDimensionFilter.js';
import { useMapTreeState } from './useMapTreeState.js';

// Re-exported so existing importers of the tree helpers keep one seam; the
// implementations live in mapTree.js (pure, unit-testable without the hook).
export { findSubtree, buildBreadcrumbPath } from './mapTree.js';

/**
 * Drill path and mode/style toggles live in the nav-stack entry (route
 * params), not component state — drilling pushes a history entry, toggling
 * replaces one (see the app's map route renderer), and browser back/forward
 * and the breadcrumb restore them. Defaults apply when a fresh tab entry
 * carries no params yet. Standalone renders (tests) may pass no nav
 * bundle; the setters then no-op.
 */
function useMapNavParams(nav) {
  const {
    path: currentPath = '',
    vizStyle = 'zoompack',
    viewMode = 'health',
    galaxyMode = 'filesystem',
    onPathChange, onVizStyleChange, onViewModeChange, onGalaxyModeChange,
  } = nav || {};
  return {
    currentPath, vizStyle, viewMode, galaxyMode,
    setCurrentPath: (p) => onPathChange?.(p),
    setVizStyle: (v) => onVizStyleChange?.(v),
    setViewMode: (v) => onViewModeChange?.(v),
    setGalaxyMode: (v) => onGalaxyModeChange?.(v),
  };
}

/** Fresh tab click drops the cache; round-tripping through a detail view
 * does not change tabKey, so cached state survives unmount/remount. */
function useMapTabCache(selectedProject, tabKey) {
  const lastTabKeyRef = useRef(tabKey);
  if (lastTabKeyRef.current !== tabKey) {
    resetCachedScope('map', selectedProject);
    lastTabKeyRef.current = tabKey;
  }
  return readCachedState('map', selectedProject, { selectedDimensionsArr: [] });
}

/** Assembles the hook's return object — kept as one literal (not spread
 * pieces) so the return-object keys stay an explicit, reviewable contract
 * for every consumer of useMapPageState. */
function buildMapPageResult({
  allDimensions, viewMode, setViewMode, vizStyle, setVizStyle, galaxyMode, setGalaxyMode,
  dimensionNames, effectiveSelected, handleToggleDimension, currentNode, fullTree, currentPath,
  setCurrentPath, filteredDimensions, handleDrillDown, callbacks, handleBreadcrumbNav,
  showLabels, setShowLabels, darkMode, setDarkMode, breadcrumb, tabKey, projectName, standardTypes,
}) {
  return {
    allDimensions,
    viewState: { viewMode, setViewMode, vizStyle, setVizStyle },
    galaxyState: { galaxyMode, setGalaxyMode },
    dimensionState: { allDimensions: dimensionNames, selectedDimensions: effectiveSelected, onToggleDimension: handleToggleDimension },
    vizState: { vizStyle, viewMode, galaxyMode, setGalaxyMode },
    treeState: { node: currentNode, fullTree, currentPath, onPathChange: setCurrentPath },
    dimensions: filteredDimensions,
    callbacks: {
      onDrillDown: handleDrillDown,
      onFileClick: (treeNode) => {
        if (!callbacks?.onNavigate) return;
        callbacks.onNavigate('file', { file: treeNodeToFileObj(treeNode), sourceTab: 'map' });
      },
      onNavigate: callbacks?.onNavigate,
      onBreadcrumbNav: handleBreadcrumbNav,
    },
    display: {
      showLabels, setShowLabels,
      darkMode, setDarkMode,
      breadcrumb,
      resetKey: tabKey,
      projectName,
      standardTypes,
    },
    currentNode,
  };
}

/**
 * Map page state, as composition: DOM sizing (useDashboardFullHeight), the
 * standards fetch (useVisibleStandards), display prefs (useMapDisplayPrefs),
 * the dimension filter (useMapDimensionFilter), the tree (useMapTreeState),
 * and storage via the shared adapters (adapters/storage.js + pageStateCache).
 */
export default function useMapPageState({ data, callbacks, nav, tabKey = 0 }) {
  const selectedProject = data?.projectName || data?.selectedProject || '__map__';
  const {
    currentPath, vizStyle, viewMode, galaxyMode,
    setCurrentPath, setVizStyle, setViewMode, setGalaxyMode,
  } = useMapNavParams(nav);
  const cached = useMapTabCache(selectedProject, tabKey);

  // Lock parent to viewport height while map is active.
  useDashboardFullHeight();

  // Refresh data on mount and on tab re-click
  useEffect(() => {
    callbacks?.onRefresh?.();
  }, [tabKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // Standard types for galaxy constellation grouping.
  const { standardTypes } = useVisibleStandards();

  const allDimensions = data?.accumulated?.dimensions || data?.dashboard?.dimensions || [];

  const { showLabels, setShowLabels, darkMode, setDarkMode } = useMapDisplayPrefs();

  const { dimensionNames, effectiveSelected, handleToggleDimension, filteredDimensions } = useMapDimensionFilter({
    allDimensions, selectedProject, cachedSelectedArr: cached.selectedDimensionsArr,
  });

  const { fullTree, currentNode, breadcrumb, handleDrillDown, handleBreadcrumbNav } = useMapTreeState({
    filteredDimensions, currentPath, setCurrentPath,
  });

  return buildMapPageResult({
    allDimensions, viewMode, setViewMode, vizStyle, setVizStyle, galaxyMode, setGalaxyMode,
    dimensionNames, effectiveSelected, handleToggleDimension, currentNode, fullTree, currentPath,
    setCurrentPath, filteredDimensions, handleDrillDown, callbacks, handleBreadcrumbNav,
    showLabels, setShowLabels, darkMode, setDarkMode, breadcrumb, tabKey, projectName: data?.projectName, standardTypes,
  });
}
