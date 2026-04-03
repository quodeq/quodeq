import { useState, useMemo } from 'react';
import { buildFileTree } from '../utils/fileTree.js';
import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';
import TreemapView from './TreemapView.jsx';
import HeatGridView from './HeatGridView.jsx';

const VIEW_MODES = [
  { id: 'violations', label: 'Violations' },
  { id: 'health', label: 'Health' },
];

const VIZ_STYLES = [
  { id: 'treemap', label: 'Treemap', enabled: true },
  { id: 'heatgrid', label: 'Heat Grid', enabled: true },
  { id: 'sunburst', label: 'Sunburst', enabled: false },
  { id: 'bubbles', label: 'Bubbles', enabled: false },
];

function DimensionFilter({ allDimensions, selectedDimensions, onToggle }) {
  if (allDimensions.length <= 1) return null;
  return (
    <div className="map-pill-group map-dim-filter">
      {allDimensions.map((dim) => (
        <button
          key={dim}
          type="button"
          className={`map-pill map-dim-pill${selectedDimensions.has(dim) ? ' active' : ''}`}
          onClick={() => onToggle(dim)}
        >
          {dim}
        </button>
      ))}
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
      <div className="page-header">
        <h2 className="page-title">Map</h2>
        <span className="page-count">
          {currentNode.violations} violation{currentNode.violations !== 1 ? 's' : ''} · {currentNode.compliance} compliance
        </span>
      </div>
      <MapControls viewMode={viewMode} setViewMode={setViewMode} vizStyle={vizStyle} setVizStyle={setVizStyle} allDimensions={dimensionNames} selectedDimensions={effectiveSelected} onToggleDimension={handleToggleDimension} />
      <MapBreadcrumb path={breadcrumb} onNavigate={handleBreadcrumbNav} onBack={handleBack} />
      <div className="map-viz-container">
        {vizStyle === 'treemap' && <TreemapView node={currentNode} viewMode={viewMode} onDrillDown={handleDrillDown} />}
        {vizStyle === 'heatgrid' && <HeatGridView node={currentNode} viewMode={viewMode} onDrillDown={handleDrillDown} />}
        {vizStyle === 'sunburst' && <p className="empty-state">Sunburst — coming soon</p>}
        {vizStyle === 'bubbles' && <p className="empty-state">Bubbles — coming soon</p>}
      </div>
    </div>
  );
}
