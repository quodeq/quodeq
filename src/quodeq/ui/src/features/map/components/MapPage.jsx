import { useState, useRef, useEffect } from 'react';
import {
  RiskMatrixView, ZoomablePackView,
  GalaxyView, GalaxyFolderView, VizBreadcrumb,
} from '../viz/index.js';
import { complianceRatio } from '../../../utils/formatters.js';
import useMapPageState from './useMapPageState.js';

function getAppThemeInfo() {
  const attr = document.documentElement.getAttribute('data-theme') || '';
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  const isDark = attr.includes('dark') || (!attr.includes('light') && prefersDark);
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

function MapControls({ viewState, galaxyState, dimensionState }) {
  const { viewMode, setViewMode, vizStyle, setVizStyle } = viewState;
  const { galaxyMode, setGalaxyMode } = galaxyState;
  const { allDimensions, selectedDimensions, onToggleDimension } = dimensionState;
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

function MapVizContainer({ vizState, treeState, dimensions, callbacks, display }) {
  const { vizStyle, viewMode, galaxyMode, setGalaxyMode } = vizState;
  const { node, fullTree, currentPath, onPathChange } = treeState;
  const { onDrillDown, onFileClick, onNavigate, onBreadcrumbNav } = callbacks;
  const { showLabels, setShowLabels, darkMode, setDarkMode, breadcrumb, resetKey, projectName, standardTypes } = display;
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

export default function MapPage(props) {
  const state = useMapPageState(props);

  if (state.allDimensions.length === 0) {
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
          <strong>{state.currentNode.violations}</strong> violation{state.currentNode.violations !== 1 ? 's' : ''} · <strong>{complianceRatio(state.currentNode.violations, state.currentNode.compliance)}</strong> ratio
        </span>
        <MapControls viewState={state.viewState} galaxyState={state.galaxyState} dimensionState={state.dimensionState} />
      </div>
      <MapVizContainer vizState={state.vizState} treeState={state.treeState} dimensions={state.dimensions} callbacks={state.callbacks} display={state.display} />
    </div>
  );
}
