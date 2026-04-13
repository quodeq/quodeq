import { useState, useMemo, useRef, useEffect } from 'react';
import {
  buildFileTree, treeNodeToFileObj,
  RiskMatrixView, ZoomablePackView,
  GalaxyView, GalaxyFolderView, VizBreadcrumb,
} from '../viz/index.js';
import { complianceRatio } from '../../../utils/formatters.js';
import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';
import { listStandards } from '../../../api/standards.js';

let _savedMapPath = '';
let _savedVizStyle = 'zoompack';
let _savedViewMode = 'health';
let _savedGalaxyMode = 'filesystem';

const MAP_LABELS_KEY = 'quodeq-map-labels';
const MAP_DARK_KEY = 'quodeq-map-dark';

function getAppThemeInfo() {
  const attr = document.documentElement.getAttribute('data-theme') || '';
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  const isDark = attr.includes('dark') || (!attr.includes('light') && prefersDark);
  // Extract family: "neo-dark" → "neo", "dark" → "daruma", "" → "daruma"
  const family = attr.replace(/-?(dark|light)$/, '') || 'daruma';
  return { isDark, family, attr };
}

function isAppDark() {
  return getAppThemeInfo().isDark;
}

function getDarkThemeAttr() {
  const { family } = getAppThemeInfo();
  return family === 'daruma' ? 'dark' : `${family}-dark`;
}

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

function MapBreadcrumb({ path, onNavigate, projectName }) {
  const segments = [{ name: projectName || 'Project', path: '' }, ...path];
  return (
    <VizBreadcrumb
      items={segments.map((seg, i) => ({ label: seg.name, onClick: i < segments.length - 1 ? () => onNavigate(seg.path) : undefined }))}
    />
  );
}

function findSubtree(root, path) {
  if (!path) return root;
  function walk(node, depth = 0) {
    if (depth > 64) return null;
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

function MapVizContainer({ vizStyle, viewMode, galaxyMode, setGalaxyMode, node, fullTree, currentPath, onPathChange, dimensions, onDrillDown, onFileClick, onNavigate, showLabels, setShowLabels, darkMode, setDarkMode, breadcrumb, onBreadcrumbNav, resetKey, projectName, standardTypes }) {
  return (
    <div className="map-viz-container" {...(darkMode && !isAppDark() ? { 'data-theme': getDarkThemeAttr() } : {})}>
      {vizStyle !== 'galaxy' && <MapBreadcrumb path={breadcrumb} onNavigate={onBreadcrumbNav} projectName={projectName} />}
      <div className="map-viz-toggles">
        <label className="map-label-toggle">
          <input type="checkbox" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)} />
          Labels
        </label>
        {!isAppDark() && (
          <label className="map-label-toggle">
            <input type="checkbox" checked={!darkMode} onChange={(e) => setDarkMode(!e.target.checked)} />
            Light
          </label>
        )}
      </div>
      {vizStyle === 'riskmatrix' && <RiskMatrixView node={node} onDrillDown={onDrillDown} onFileClick={onFileClick} showLabels={showLabels} />}
      {vizStyle === 'zoompack' && <ZoomablePackView node={fullTree} viewMode={viewMode} onDrillDown={onDrillDown} onFileClick={onFileClick} showLabels={showLabels} resetKey={resetKey} currentPath={currentPath} />}
      {vizStyle === 'galaxy' && galaxyMode === 'standards' && <GalaxyView dimensions={dimensions} onNavigate={onNavigate} showLabels={showLabels} setShowLabels={setShowLabels} darkMode={darkMode} resetKey={resetKey} projectName={projectName} standardTypes={standardTypes} />}
      {vizStyle === 'galaxy' && galaxyMode === 'filesystem' && <GalaxyFolderView node={fullTree} currentPath={currentPath} onPathChange={onPathChange} onFileClick={onFileClick} onNavigate={onNavigate} showLabels={showLabels} setShowLabels={setShowLabels} darkMode={darkMode} resetKey={resetKey} projectName={projectName} />}
    </div>
  );
}

let _lastTabKey = null;

export default function MapPage({ data, callbacks, tabKey = 0 }) {
  // Reset only on fresh tab click (tabKey changed), not on back from detail
  const isFreshTabClick = _lastTabKey !== null && tabKey !== _lastTabKey;
  _lastTabKey = tabKey;
  if (isFreshTabClick) _savedMapPath = '';

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
  const [viewMode, _setViewMode] = useState(_savedViewMode);
  const setViewMode = (v) => { _savedViewMode = v; _setViewMode(v); };
  const [vizStyle, _setVizStyle] = useState(_savedVizStyle);
  const setVizStyle = (v) => { _savedVizStyle = v; _setVizStyle(v); };
  const [galaxyMode, _setGalaxyMode] = useState(_savedGalaxyMode);
  const setGalaxyMode = (v) => { _savedGalaxyMode = v; _setGalaxyMode(v); };
  const [showLabels, _setShowLabels] = useState(() => { try { const v = localStorage.getItem(MAP_LABELS_KEY); return v === null ? true : v === '1'; } catch { return true; } });
  const setShowLabels = (v) => { _setShowLabels(v); try { localStorage.setItem(MAP_LABELS_KEY, v ? '1' : '0'); } catch {} };
  // Dark mode: in dark app theme → always dark (no toggle).
  // In light app theme → default dark, user can switch to light, remembered across tabs.
  const [darkMode, _setDarkMode] = useState(() => {
    if (isAppDark()) return true;
    try { const v = localStorage.getItem(MAP_DARK_KEY); return v === null ? true : v === '1'; } catch { return true; }
  });
  const setDarkMode = (v) => { _setDarkMode(v); try { localStorage.setItem(MAP_DARK_KEY, v ? '1' : '0'); } catch {} };
  // Reset when app theme changes
  useEffect(() => {
    const obs = new MutationObserver(() => {
      if (isAppDark()) { _setDarkMode(true); }
      else { try { const v = localStorage.getItem(MAP_DARK_KEY); _setDarkMode(v === null ? true : v === '1'); } catch { _setDarkMode(true); } }
    });
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => obs.disconnect();
  }, []);
  const [currentPath, _setCurrentPath] = useState(_savedMapPath);
  const setCurrentPath = (p) => { _savedMapPath = p; _setCurrentPath(p); };

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
      <MapVizContainer vizStyle={vizStyle} viewMode={viewMode} galaxyMode={galaxyMode} setGalaxyMode={setGalaxyMode} node={currentNode} fullTree={fullTree} currentPath={currentPath} onPathChange={setCurrentPath} dimensions={filteredDimensions} onDrillDown={handleDrillDown} onFileClick={handleFileClick} onNavigate={callbacks?.onNavigate} showLabels={showLabels} setShowLabels={setShowLabels} darkMode={darkMode} setDarkMode={setDarkMode} breadcrumb={breadcrumb} onBreadcrumbNav={handleBreadcrumbNav} resetKey={tabKey} projectName={data?.projectName} standardTypes={standardTypes} />
    </div>
  );
}
