import { useState, useMemo, useRef, useEffect } from 'react';
import { buildFileTree, treeNodeToFileObj } from '../viz/index.js';
import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';
import { listStandards } from '../../../api/standards.js';

const MAP_LABELS_KEY = 'quodeq-map-labels';
const MAP_DARK_KEY = 'quodeq-map-dark';
const MAX_TREE_DEPTH = 64;

function isAppDark() {
  const attr = document.documentElement.getAttribute('data-theme') || '';
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  return attr.includes('dark') || (!attr.includes('light') && prefersDark);
}

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
  const savedMapPathRef = useRef('');
  // UI defaults for map visualisation mode. These are presentation-layer
  // defaults only; they do not affect evaluation logic or server behaviour.
  const savedVizStyleRef = useRef('zoompack');
  const savedViewModeRef = useRef('health');
  const savedGalaxyModeRef = useRef('filesystem');
  const lastTabKeyRef = useRef(null);

  // Reset only on fresh tab click (tabKey changed), not on back from detail
  const isFreshTabClick = lastTabKeyRef.current !== null && tabKey !== lastTabKeyRef.current;
  lastTabKeyRef.current = tabKey;
  if (isFreshTabClick) savedMapPathRef.current = '';

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
  const [viewMode, _setViewMode] = useState(savedViewModeRef.current);
  const setViewMode = (v) => { savedViewModeRef.current = v; _setViewMode(v); };
  const [vizStyle, _setVizStyle] = useState(savedVizStyleRef.current);
  const setVizStyle = (v) => { savedVizStyleRef.current = v; _setVizStyle(v); };
  const [galaxyMode, _setGalaxyMode] = useState(savedGalaxyModeRef.current);
  const setGalaxyMode = (v) => { savedGalaxyModeRef.current = v; _setGalaxyMode(v); };
  const [showLabels, _setShowLabels] = useState(() => { try { const v = localStorage.getItem(MAP_LABELS_KEY); return v === null ? true : v === '1'; } catch { return true; } });
  const setShowLabels = (v) => { _setShowLabels(v); try { localStorage.setItem(MAP_LABELS_KEY, v ? '1' : '0'); } catch {} };
  const [darkMode, _setDarkMode] = useState(() => {
    if (isAppDark()) return true;
    try { const v = localStorage.getItem(MAP_DARK_KEY); return v === null ? true : v === '1'; } catch { return true; }
  });
  const setDarkMode = (v) => { _setDarkMode(v); try { localStorage.setItem(MAP_DARK_KEY, v ? '1' : '0'); } catch {} };
  useEffect(() => {
    const obs = new MutationObserver(() => {
      if (isAppDark()) { _setDarkMode(true); }
      else { try { const v = localStorage.getItem(MAP_DARK_KEY); _setDarkMode(v === null ? true : v === '1'); } catch { _setDarkMode(true); } }
    });
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => obs.disconnect();
  }, []);
  const [currentPath, _setCurrentPath] = useState(savedMapPathRef.current);
  const setCurrentPath = (p) => { savedMapPathRef.current = p; _setCurrentPath(p); };

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

  // Selected dimensions filter — defaults to all visible
  const [selectedDimensions, setSelectedDimensions] = useState(() => new Set());
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
