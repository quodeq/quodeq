import { useState, useMemo, useRef, useEffect } from 'react';
import { buildFileTree, treeNodeToFileObj } from '../viz/index.js';
import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';
import { readString, writeString } from '../../../adapters/storage.js';
import { readCachedState, writeCachedState, resetCachedScope } from '../../../utils/pageStateCache.js';
import { useThemeIsDark } from '../../../hooks/useThemeIsDark.js';
import { findSubtree, buildBreadcrumbPath } from './mapTree.js';
import { useDashboardFullHeight } from './useDashboardFullHeight.js';
import { useVisibleStandards } from './useVisibleStandards.js';

// Re-exported so existing importers of the tree helpers keep one seam; the
// implementations live in mapTree.js (pure, unit-testable without the hook).
export { findSubtree, buildBreadcrumbPath } from './mapTree.js';

const MAP_LABELS_KEY = 'quodeq-map-labels';
const MAP_DARK_KEY = 'quodeq-map-dark';

/**
 * Map page state, as composition: DOM sizing (useDashboardFullHeight), the
 * standards fetch (useVisibleStandards), storage via the shared adapters
 * (adapters/storage.js + pageStateCache), and the pure tree logic (mapTree.js).
 */
export default function useMapPageState({ data, callbacks, nav, tabKey = 0 }) {
  const selectedProject = data?.projectName || data?.selectedProject || '__map__';

  // Drill path and mode/style toggles live in the nav-stack entry (route
  // params), not component state — drilling pushes a history entry, toggling
  // replaces one (see the app's map route renderer), and browser back/forward
  // and the breadcrumb restore them. Defaults apply when a fresh tab entry
  // carries no params yet. Standalone renders (tests) may pass no nav
  // bundle; the setters then no-op.
  const {
    path: currentPath = '',
    vizStyle = 'zoompack',
    viewMode = 'health',
    galaxyMode = 'filesystem',
    onPathChange, onVizStyleChange, onViewModeChange, onGalaxyModeChange,
  } = nav || {};
  const setCurrentPath = (p) => onPathChange?.(p);
  const setVizStyle = (v) => onVizStyleChange?.(v);
  const setViewMode = (v) => onViewModeChange?.(v);
  const setGalaxyMode = (v) => onGalaxyModeChange?.(v);

  // Fresh tab click drops the cache; round-tripping through a detail view
  // does not change tabKey, so cached state survives unmount/remount.
  const lastTabKeyRef = useRef(tabKey);
  if (lastTabKeyRef.current !== tabKey) {
    resetCachedScope('map', selectedProject);
    lastTabKeyRef.current = tabKey;
  }

  const cached = readCachedState('map', selectedProject, {
    selectedDimensionsArr: [],
  });

  // Lock parent to viewport height while map is active.
  useDashboardFullHeight();

  // Refresh data on mount and on tab re-click
  useEffect(() => {
    callbacks?.onRefresh?.();
  }, [tabKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // Standard types for galaxy constellation grouping.
  const { standardTypes } = useVisibleStandards();

  const allDimensions = data?.accumulated?.dimensions || data?.dashboard?.dimensions || [];
  const [showLabels, _setShowLabels] = useState(() => {
    const v = readString(MAP_LABELS_KEY);
    return v === null ? true : v === '1';
  });
  const setShowLabels = (v) => { _setShowLabels(v); writeString(MAP_LABELS_KEY, v ? '1' : '0'); };
  const appIsDark = useThemeIsDark();
  const [darkMode, _setDarkMode] = useState(() => {
    if (appIsDark) return true;
    return readString(MAP_DARK_KEY) === '1';
  });
  const setDarkMode = (v) => { _setDarkMode(v); writeString(MAP_DARK_KEY, v ? '1' : '0'); };
  // A dark app theme always forces dark viz; back on light, restore the
  // user's stored viz preference (defaulting to light when none is stored).
  useEffect(() => {
    if (appIsDark) { _setDarkMode(true); }
    else { _setDarkMode(readString(MAP_DARK_KEY) === '1'); }
  }, [appIsDark]);
  // Tab re-click needs no path reset here anymore: navTab creates a fresh
  // entry with no path param, so the controlled currentPath above is already
  // '' (and the refresh-on-tabKey effect above covers the data refresh).

  // Get visible standards and available dimension names
  const visibleIds = useMemo(() => new Set(readVisibleStandardIds()), [allDimensions]);
  const visibleDimensions = useMemo(
    () => allDimensions.filter((d) => visibleIds.has((d.dimension || '').toLowerCase())),
    [allDimensions, visibleIds]
  );
  const dimensionNames = useMemo(
    () => visibleDimensions.map((d) => d.dimension).filter(Boolean).sort(),
    [visibleDimensions]
  );

  // Selected dimensions filter — defaults to all visible. Empty set means
  // "no filter applied" (show all). Persisted across unmount as an array.
  const [selectedDimensions, _setSelectedDimensions] = useState(() => new Set(cached.selectedDimensionsArr));
  const setSelectedDimensions = (updater) => {
    _setSelectedDimensions((prev) => {
      const next = typeof updater === 'function' ? updater(prev) : updater;
      writeCachedState('map', selectedProject, { selectedDimensionsArr: Array.from(next) });
      return next;
    });
  };
  const effectiveSelected = useMemo(
    () => selectedDimensions.size === 0 ? new Set(dimensionNames) : selectedDimensions,
    [selectedDimensions, dimensionNames]
  );

  const handleToggleDimension = (dim) => {
    setSelectedDimensions((prev) => {
      const base = prev.size === 0 ? new Set(dimensionNames) : new Set(prev);
      if (base.has(dim)) {
        base.delete(dim);
        if (base.size === 0) return new Set();
      } else {
        base.add(dim);
      }
      if (base.size === dimensionNames.length) return new Set();
      return base;
    });
  };

  // Filter dimensions by selection
  const filteredDimensions = useMemo(
    () => visibleDimensions.filter((d) => effectiveSelected.has(d.dimension)),
    [visibleDimensions, effectiveSelected]
  );

  const fullTree = useMemo(() => buildFileTree(filteredDimensions), [filteredDimensions]);
  const currentNode = useMemo(() => findSubtree(fullTree, currentPath), [fullTree, currentPath]);
  const breadcrumb = useMemo(() => buildBreadcrumbPath(fullTree, currentPath), [fullTree, currentPath]);

  const handleDrillDown = (nodePath) => setCurrentPath(nodePath);
  const handleBreadcrumbNav = (path) => setCurrentPath(path);

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
      projectName: data?.projectName,
      standardTypes,
    },
    currentNode,
  };
}
