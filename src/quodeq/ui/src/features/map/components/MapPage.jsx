import { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import { buildFileTree } from '../utils/fileTree.js';
import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';
import TreemapView from './TreemapView.jsx';
import HeatGridView from './HeatGridView.jsx';
import SunburstView from './SunburstView.jsx';
import BubblePackView from './BubblePackView.jsx';

const VIEW_MODES = [
  { id: 'violations', label: 'Violations' },
  { id: 'health', label: 'Health' },
];

const VIZ_STYLES = [
  { id: 'treemap', label: 'Treemap', enabled: true },
  { id: 'heatgrid', label: 'Heat Grid', enabled: true },
  { id: 'sunburst', label: 'Sunburst', enabled: true },
  { id: 'bubbles', label: 'Bubbles', enabled: true },
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

function MapControls({ viewMode, setViewMode, vizStyle, setVizStyle, allDimensions, selectedDimensions, onToggleDimension }) {
  return (
    <div className="map-controls">
      <div className="map-pill-group">
        {VIEW_MODES.map((m) => (
          <button key={m.id} type="button" className={`map-pill${viewMode === m.id ? ' active' : ''}`} onClick={() => setViewMode(m.id)}>
            {m.label}
          </button>
        ))}
      </div>
      <div className="map-pill-group">
        {VIZ_STYLES.map((s) => (
          <button key={s.id} type="button" className={`map-pill${vizStyle === s.id ? ' active' : ''}${!s.enabled ? ' disabled' : ''}`} onClick={() => s.enabled && setVizStyle(s.id)} title={!s.enabled ? 'Coming soon' : ''}>
            {s.label}
          </button>
        ))}
      </div>
      <DimensionFilter allDimensions={allDimensions} selectedDimensions={selectedDimensions} onToggle={onToggleDimension} />
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
  const parts = path.split('/').filter(Boolean);
  let node = root;
  for (const part of parts) {
    const child = node.children.find((c) => c.name === part);
    if (!child) return root;
    node = child;
  }
  return node;
}

function buildBreadcrumbPath(path) {
  if (!path) return [];
  const parts = path.split('/').filter(Boolean);
  return parts.map((name, i) => ({ name, path: parts.slice(0, i + 1).join('/') }));
}

function MapVizContainer({ vizStyle, viewMode, node, onDrillDown }) {
  const ref = useRef(null);
  const [height, setHeight] = useState(400);

  useEffect(() => {
    if (!ref.current) return;
    const observer = new ResizeObserver(([entry]) => {
      const h = Math.floor(entry.contentRect.height);
      if (h > 0) setHeight(h);
    });
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={ref} className="map-viz-container">
      {vizStyle === 'treemap' && <TreemapView node={node} viewMode={viewMode} onDrillDown={onDrillDown} containerHeight={height} />}
      {vizStyle === 'heatgrid' && <HeatGridView node={node} viewMode={viewMode} onDrillDown={onDrillDown} />}
      {vizStyle === 'sunburst' && <SunburstView node={node} viewMode={viewMode} onDrillDown={onDrillDown} />}
      {vizStyle === 'bubbles' && <BubblePackView node={node} viewMode={viewMode} onDrillDown={onDrillDown} />}
    </div>
  );
}

export default function MapPage({ data, callbacks }) {
  const allDimensions = data?.accumulated?.dimensions || data?.dashboard?.dimensions || [];
  const [viewMode, setViewMode] = useState('violations');
  const [vizStyle, setVizStyle] = useState('treemap');
  const [currentPath, setCurrentPath] = useState('');

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
  const breadcrumb = useMemo(() => buildBreadcrumbPath(currentPath), [currentPath]);

  const handleDrillDown = (nodePath) => setCurrentPath(nodePath);
  const handleBreadcrumbNav = (path) => setCurrentPath(path);
  const handleBack = () => {
    if (!currentPath) return;
    const parts = currentPath.split('/').filter(Boolean);
    parts.pop();
    setCurrentPath(parts.join('/'));
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
          <strong>{currentNode.violations}</strong> violation{currentNode.violations !== 1 ? 's' : ''} · <strong>{currentNode.compliance}</strong> compliance
        </span>
        <MapControls viewMode={viewMode} setViewMode={setViewMode} vizStyle={vizStyle} setVizStyle={setVizStyle} allDimensions={dimensionNames} selectedDimensions={effectiveSelected} onToggleDimension={handleToggleDimension} />
      </div>
      <MapBreadcrumb path={breadcrumb} onNavigate={handleBreadcrumbNav} onBack={handleBack} />
      <MapVizContainer vizStyle={vizStyle} viewMode={viewMode} node={currentNode} onDrillDown={handleDrillDown} />
    </div>
  );
}
