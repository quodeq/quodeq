import { useState, useMemo, useRef, useEffect } from 'react';
import { buildFileTree, treeNodeToFileObj } from '../utils/fileTree.js';
import { complianceRatio } from '../../../utils/formatters.js';
import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';
import RiskMatrixView from './RiskMatrixView.jsx';
import ZoomablePackView, { resetSavedFocus } from './ZoomablePackView.jsx';
import GalaxyView from './GalaxyView.jsx';
import GalaxyFolderView from './GalaxyFolderView.jsx';

let _savedMapPath = '';
let _savedVizStyle = 'zoompack';
let _savedViewMode = 'health';
let _savedGalaxyMode = 'filesystem';

const VIEW_MODES = [
  { id: 'health', label: 'Health' },
  { id: 'violations', label: 'Violations' },
];

const VIZ_STYLES = [
  { id: 'zoompack', label: 'Circle Pack', enabled: true },
  { id: 'galaxy', label: 'Galaxy', enabled: true },
  { id: 'riskmatrix', label: 'Risk Matrix', enabled: true },
];

const GALAXY_MODES = [
  { id: 'filesystem', label: 'File System' },
  { id: 'standards', label: 'Standards' },
];

function DimensionFilter({ allDimensions, selectedDimensions, onToggle }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const handleClickOutside = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [open]);

  if (allDimensions.length <= 1) return null;

  const activeCount = selectedDimensions.size === allDimensions.length ? allDimensions.length : selectedDimensions.size;
  const label = activeCount === allDimensions.length ? 'All dimensions' : `${activeCount} of ${allDimensions.length}`;

  return (
    <div className="map-filter-wrap" ref={ref}>
      <button type="button" className="map-pill map-filter-btn" onClick={() => setOpen((v) => !v)}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
        </svg>
        {label}
      </button>
      {open && (
        <div className="map-filter-dropdown">
          {allDimensions.map((dim) => (
            <label key={dim} className="map-filter-item">
              <input type="checkbox" checked={selectedDimensions.has(dim)} onChange={() => onToggle(dim)} />
              <span>{dim}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

function MapControls({ viewMode, setViewMode, vizStyle, setVizStyle, galaxyMode, setGalaxyMode, allDimensions, selectedDimensions, onToggleDimension }) {
  return (
    <div className="map-controls">
      <DimensionFilter allDimensions={allDimensions} selectedDimensions={selectedDimensions} onToggle={onToggleDimension} />
      {vizStyle === 'zoompack' && (
        <div className="map-pill-group">
          {VIEW_MODES.map((m) => (
            <button key={m.id} type="button" className={`map-pill${viewMode === m.id ? ' active' : ''}`} onClick={() => setViewMode(m.id)}>
              {m.label}
            </button>
          ))}
        </div>
      )}
      {vizStyle === 'galaxy' && (
        <div className="map-pill-group">
          {GALAXY_MODES.map((m) => (
            <button key={m.id} type="button" className={`map-pill${galaxyMode === m.id ? ' active' : ''}`} onClick={() => setGalaxyMode(m.id)}>
              {m.label}
            </button>
          ))}
        </div>
      )}
      <div className="map-pill-group">
        {VIZ_STYLES.map((s) => (
          <button key={s.id} type="button" className={`map-pill${vizStyle === s.id ? ' active' : ''}${!s.enabled ? ' disabled' : ''}`} onClick={() => s.enabled && setVizStyle(s.id)} title={!s.enabled ? 'Coming soon' : ''}>
            {s.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function MapBreadcrumb({ path, onNavigate, onBack }) {
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

function findSubtree(root, path) {
  if (!path) return root;
  // Walk the tree matching by node.path (handles collapsed names like "java/app/src")
  function walk(node) {
    if (node.path === path) return node;
    for (const child of node.children) {
      if (path === child.path || path.startsWith(child.path + '/')) {
        const found = walk(child);
        if (found) return found;
      }
    }
    return null;
  }
  return walk(root) || root;
}

function findParentPath(root, currentPath) {
  // Find the parent node's path in the (possibly collapsed) tree
  if (!currentPath) return '';
  function walk(node) {
    for (const child of node.children) {
      if (child.path === currentPath) return node.path;
      if (currentPath.startsWith(child.path + '/')) {
        const found = walk(child);
        if (found !== null) return found;
      }
    }
    return null;
  }
  return walk(root) ?? '';
}

function buildBreadcrumbPath(root, path) {
  if (!path) return [];
  // Walk the collapsed tree to build breadcrumb from actual node names
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

function MapVizContainer({ vizStyle, viewMode, galaxyMode, setGalaxyMode, node, dimensions, onDrillDown, onFileClick, onNavigate, showLabels, setShowLabels, breadcrumb, onBreadcrumbNav, onBack, resetKey, projectName }) {
  return (
    <div className="map-viz-container">
      {vizStyle !== 'galaxy' && <MapBreadcrumb path={breadcrumb} onNavigate={onBreadcrumbNav} onBack={onBack} />}
      {vizStyle !== 'galaxy' && (
        <label className="map-label-toggle">
          <input type="checkbox" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)} />
          Labels
        </label>
      )}
      {vizStyle === 'riskmatrix' && <RiskMatrixView node={node} onDrillDown={onDrillDown} onFileClick={onFileClick} showLabels={showLabels} />}
      {vizStyle === 'zoompack' && <ZoomablePackView node={node} viewMode={viewMode} onDrillDown={onDrillDown} onFileClick={onFileClick} showLabels={showLabels} resetKey={resetKey} />}
      {vizStyle === 'galaxy' && galaxyMode === 'standards' && <GalaxyView dimensions={dimensions} onNavigate={onNavigate} showLabels={showLabels} setShowLabels={setShowLabels} resetKey={resetKey} projectName={projectName} />}
      {vizStyle === 'galaxy' && galaxyMode === 'filesystem' && <GalaxyFolderView node={node} onFileClick={onFileClick} onNavigate={onNavigate} showLabels={showLabels} setShowLabels={setShowLabels} resetKey={resetKey} projectName={projectName} />}
    </div>
  );
}

let _lastTabKey = null;

function resetMapSavedState() {
  _savedMapPath = '';
  resetSavedFocus();
}

export default function MapPage({ data, callbacks, tabKey = 0 }) {
  // Reset only on fresh tab click (tabKey changed), not on back from detail
  const isFreshTabClick = _lastTabKey !== null && tabKey !== _lastTabKey;
  _lastTabKey = tabKey;
  if (isFreshTabClick) resetMapSavedState();

  // Lock parent to viewport height while map is active
  useEffect(() => {
    const dashboard = document.querySelector('.dashboard');
    if (dashboard) {
      dashboard.classList.add('dashboard--fullheight');
      return () => dashboard.classList.remove('dashboard--fullheight');
    }
  }, []);

  // Refresh data on mount (ensures fresh data after returning from detail pages) and on tab re-click
  useEffect(() => {
    callbacks?.onRefresh?.();
  }, [tabKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const allDimensions = data?.accumulated?.dimensions || data?.dashboard?.dimensions || [];
  const [viewMode, _setViewMode] = useState(_savedViewMode);
  const setViewMode = (v) => { _savedViewMode = v; _setViewMode(v); };
  const [vizStyle, _setVizStyle] = useState(_savedVizStyle);
  const setVizStyle = (v) => { _savedVizStyle = v; _setVizStyle(v); };
  const [galaxyMode, _setGalaxyMode] = useState(_savedGalaxyMode);
  const setGalaxyMode = (v) => { _savedGalaxyMode = v; _setGalaxyMode(v); };
  const [showLabels, setShowLabels] = useState(false);
  const [currentPath, _setCurrentPath] = useState(_savedMapPath);
  const setCurrentPath = (p) => { _savedMapPath = p; _setCurrentPath(p); };

  // Animate back to root when tab is re-clicked while already on map
  const prevTabKey = useRef(tabKey);
  useEffect(() => {
    if (tabKey !== prevTabKey.current) {
      prevTabKey.current = tabKey;
      setCurrentPath('');
      resetSavedFocus();
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
      // If nothing explicitly selected yet, start from all-selected and toggle off this one
      const base = prev.size === 0 ? new Set(dimensionNames) : new Set(prev);
      if (base.has(dim)) {
        base.delete(dim);
        // Don't allow empty — if last one, keep it
        if (base.size === 0) return new Set();
      } else {
        base.add(dim);
      }
      // If all are selected, reset to empty (meaning "all")
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
  const handleFileClick = (treeNode) => {
    if (!callbacks?.onNavigate) return;
    callbacks.onNavigate('file', { file: treeNodeToFileObj(treeNode), sourceTab: 'map' });
  };
  const handleBreadcrumbNav = (path) => setCurrentPath(path);
  const handleBack = () => {
    if (!currentPath) return;
    setCurrentPath(findParentPath(fullTree, currentPath));
  };

  if (allDimensions.length === 0) {
    return (
      <div className="map-page">
        <div className="page-header"><h2 className="page-title">Map</h2></div>
        <div className="empty-state"><p>No evaluation data yet. Run an evaluation from the Evaluate tab.</p></div>
      </div>
    );
  }

  return (
    <div className="map-page">
      <div className="map-header">
        <h2 className="page-title">Map</h2>
        <span className="map-total-count">
          <strong>{currentNode.violations}</strong> violation{currentNode.violations !== 1 ? 's' : ''} · <strong>{complianceRatio(currentNode.violations, currentNode.compliance)}</strong> ratio
        </span>
        <MapControls viewMode={viewMode} setViewMode={setViewMode} vizStyle={vizStyle} setVizStyle={setVizStyle} galaxyMode={galaxyMode} setGalaxyMode={setGalaxyMode} allDimensions={dimensionNames} selectedDimensions={effectiveSelected} onToggleDimension={handleToggleDimension} />
      </div>
      <MapVizContainer vizStyle={vizStyle} viewMode={viewMode} galaxyMode={galaxyMode} setGalaxyMode={setGalaxyMode} node={currentNode} dimensions={filteredDimensions} onDrillDown={handleDrillDown} onFileClick={handleFileClick} onNavigate={callbacks?.onNavigate} showLabels={showLabels} setShowLabels={setShowLabels} breadcrumb={breadcrumb} onBreadcrumbNav={handleBreadcrumbNav} onBack={handleBack} resetKey={tabKey} projectName={data?.projectName} />
    </div>
  );
}
