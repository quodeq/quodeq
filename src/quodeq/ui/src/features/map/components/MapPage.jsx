import { useState, useMemo } from 'react';
import { buildFileTree } from '../utils/fileTree.js';
import TreemapView from './TreemapView.jsx';
import HeatGridView from './HeatGridView.jsx';

const VIEW_MODES = [
  { id: 'violations', label: 'Violations' },
  { id: 'compliance', label: 'Compliance' },
  { id: 'health', label: 'Health' },
];

const VIZ_STYLES = [
  { id: 'treemap', label: 'Treemap', enabled: true },
  { id: 'heatgrid', label: 'Heat Grid', enabled: true },
  { id: 'sunburst', label: 'Sunburst', enabled: false },
  { id: 'bubbles', label: 'Bubbles', enabled: false },
];

function MapControls({ viewMode, setViewMode, vizStyle, setVizStyle }) {
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
    </div>
  );
}

function MapBreadcrumb({ path, onNavigate }) {
  if (path.length === 0) return null;
  const segments = [{ name: '/', path: '' }, ...path];
  return (
    <div className="map-breadcrumb">
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
  const dimensions = data?.accumulated?.dimensions || data?.dashboard?.dimensions || [];
  const [viewMode, setViewMode] = useState('violations');
  const [vizStyle, setVizStyle] = useState('treemap');
  const [currentPath, setCurrentPath] = useState('');

  const fullTree = useMemo(() => buildFileTree(dimensions), [dimensions]);
  const currentNode = useMemo(() => findSubtree(fullTree, currentPath), [fullTree, currentPath]);
  const breadcrumb = useMemo(() => buildBreadcrumbPath(currentPath), [currentPath]);

  const handleDrillDown = (nodePath) => setCurrentPath(nodePath);
  const handleBreadcrumbNav = (path) => setCurrentPath(path);

  if (dimensions.length === 0) {
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
      <MapControls viewMode={viewMode} setViewMode={setViewMode} vizStyle={vizStyle} setVizStyle={setVizStyle} />
      <MapBreadcrumb path={breadcrumb} onNavigate={handleBreadcrumbNav} />
      <div className="map-viz-container">
        {vizStyle === 'treemap' && <TreemapView node={currentNode} viewMode={viewMode} onDrillDown={handleDrillDown} />}
        {vizStyle === 'heatgrid' && <HeatGridView node={currentNode} viewMode={viewMode} onDrillDown={handleDrillDown} />}
        {vizStyle === 'sunburst' && <p className="empty-state">Sunburst — coming soon</p>}
        {vizStyle === 'bubbles' && <p className="empty-state">Bubbles — coming soon</p>}
      </div>
    </div>
  );
}
