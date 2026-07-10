import { useState, useMemo, useRef, useEffect } from 'react';
import { buildFileTree, treeNodeToFileObj } from '../viz/index.js';
import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';
import { listStandards } from '../../../api/standards.js';
import { readCachedState, writeCachedState, resetCachedScope } from '../../../utils/pageStateCache.js';
import { useThemeIsDark } from '../../../hooks/useThemeIsDark.js';

const MAP_LABELS_KEY = 'quodeq-map-labels';
const MAP_DARK_KEY = 'quodeq-map-dark';
const MAX_TREE_DEPTH = 64;

function findSubtree(root, path) {
  if (!path) return root;
  function walk(node, depth = 0) {
    if (depth > MAX_TREE_DEPTH) return null;
    if (node.path === path) return node;
    for (const child of node.children) {
      if (path === child.path || path.startsWith(child.path + '/')) {
        const found = walk(child, depth + 1);
        if (found) return found;
      }
    }
    return null;
  }
  return walk(root) || root;
}

function buildBreadcrumbPath(root, path) {
  if (!path) return [];
  const crumbs = [];
  let node = root;
  while (node && node.path !== path) {
    const child = node.children.find((c) => path === c.path || path.startsWith(c.path + '/'));
    if (!child) break;
    crumbs.push({ name: child.name, path: child.path });
    node = child;
  }
  return crumbs;
}

export default function useMapPageState({ data, callbacks, tabKey = 0 }) {
  const selectedProject = data?.projectName || data?.selectedProject || '__map__';

  // Fresh tab click drops the cache; round-tripping through a detail view
  // does not change tabKey, so cached state survives unmount/remount.
  const lastTabKeyRef = useRef(tabKey);
  if (lastTabKeyRef.current !== tabKey) {
    resetCachedScope('map', selectedProject);
    lastTabKeyRef.current = tabKey;
  }

  const cached = readCachedState('map', selectedProject, {
    currentPath: '',
    vizStyle: 'zoompack',
    viewMode: 'health',
    galaxyMode: 'filesystem',
    selectedDimensionsArr: [],
  });

  // Lock parent to viewport height while map is active.
  // Uses document.querySelector because the .dashboard ancestor is outside
  // this component's React tree. A ref-based approach would require
  // threading a ref from a distant parent.
  useEffect(() => {
    if (typeof document === 'undefined') return;
    const dashboard = document.querySelector('.dashboard');
    if (dashboard) {
      dashboard.classList.add('dashboard--fullheight');
      return () => dashboard.classList.remove('dashboard--fullheight');
    }
  }, []);

  // Refresh data on mount and on tab re-click
  useEffect(() => {
    callbacks?.onRefresh?.();
  }, [tabKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch standard types for galaxy constellation grouping
  const [standardTypes, setStandardTypes] = useState({});
  useEffect(() => {
    listStandards().then(stds => {
      const map = {};
      stds.forEach(s => { map[(s.id || '').toLowerCase()] = s.type || 'custom'; });
      setStandardTypes(map);
    }).catch(() => {});
  }, []);

  const allDimensions = data?.accumulated?.dimensions || data?.dashboard?.dimensions || [];
  const [viewMode, _setViewMode] = useState(cached.viewMode);
  const setViewMode = (v) => { writeCachedState('map', selectedProject, { viewMode: v }); _setViewMode(v); };
  const [vizStyle, _setVizStyle] = useState(cached.vizStyle);
  const setVizStyle = (v) => { writeCachedState('map', selectedProject, { vizStyle: v }); _setVizStyle(v); };
  const [galaxyMode, _setGalaxyMode] = useState(cached.galaxyMode);
  const setGalaxyMode = (v) => { writeCachedState('map', selectedProject, { galaxyMode: v }); _setGalaxyMode(v); };
  const [showLabels, _setShowLabels] = useState(() => { try { const v = localStorage.getItem(MAP_LABELS_KEY); return v === null ? true : v === '1'; } catch { return true; } });
  const setShowLabels = (v) => { _setShowLabels(v); try { localStorage.setItem(MAP_LABELS_KEY, v ? '1' : '0'); } catch {} };
  const appIsDark = useThemeIsDark();
  const [darkMode, _setDarkMode] = useState(() => {
    if (appIsDark) return true;
    try { const v = localStorage.getItem(MAP_DARK_KEY); return v === null ? false : v === '1'; } catch { return false; }
  });
  const setDarkMode = (v) => { _setDarkMode(v); try { localStorage.setItem(MAP_DARK_KEY, v ? '1' : '0'); } catch {} };
  // A dark app theme always forces dark viz; back on light, restore the
  // user's stored viz preference (defaulting to light when none is stored).
  useEffect(() => {
    if (appIsDark) { _setDarkMode(true); }
    else { try { const v = localStorage.getItem(MAP_DARK_KEY); _setDarkMode(v === null ? false : v === '1'); } catch { _setDarkMode(false); } }
  }, [appIsDark]);
  const [currentPath, _setCurrentPath] = useState(cached.currentPath);
  const setCurrentPath = (p) => { writeCachedState('map', selectedProject, { currentPath: p }); _setCurrentPath(p); };

  // Animate back to root when tab is re-clicked while already on map
  const prevTabKey = useRef(tabKey);
  useEffect(() => {
    if (tabKey !== prevTabKey.current) {
      prevTabKey.current = tabKey;
      setCurrentPath('');
      callbacks?.onRefresh?.();
    }
  }, [tabKey]); // eslint-disable-line react-hooks/exhaustive-deps

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
