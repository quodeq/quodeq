import { useState, useRef, useEffect } from 'react';
import {
  RiskMatrixView, ZoomablePackView,
  GalaxyView, GalaxyFolderView, VizBreadcrumb,
} from '../viz/index.js';
import { complianceRatio } from '../../../utils/formatters.js';
import useMapPageState from './useMapPageState.js';
import { TermHeader } from '../../../components/terminal/index.js';
import EmptyState from '../../../components/EmptyState.jsx';
import LoadingScreen from '../../../components/LoadingScreen.jsx';
import SharedReadOnlyBadge from '../../../components/SharedReadOnlyBadge.jsx';
import { useThemeIsDark } from '../../../hooks/useThemeIsDark.js';

// data-theme attr for forcing the viz dark while the app is light: keep the
// active theme family, swap the mode suffix. Attribute values: absent =
// daruma family in system mode; otherwise 'light' | 'dark' | '<family>-<mode>'.
function getDarkThemeAttr() {
  const attr = document.documentElement.getAttribute('data-theme') || '';
  const family = attr.replace(/-?(dark|light)$/, '') || 'daruma';
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

  const isFiltered = selectedDimensions.size !== allDimensions.length;

  return (
    <div className="map-filter-wrap" ref={ref}>
      <button
        type="button"
        className={`map-pill map-filter-btn${isFiltered ? ' is-filtered' : ''}`}
        onClick={() => setOpen((v) => !v)}
        title={isFiltered ? `${selectedDimensions.size} of ${allDimensions.length} dimensions` : 'All dimensions'}
        aria-label={isFiltered ? `Dimensions (${selectedDimensions.size} of ${allDimensions.length} active)` : 'Dimensions'}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
        </svg>
        Dimensions
        {isFiltered && <span className="map-filter-btn__dot" aria-hidden="true" />}
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
            <button key={m.id} type="button" className={`map-pill${viewMode === m.id ? ' active' : ''}`} onClick={() => setViewMode(m.id)} aria-pressed={viewMode === m.id}>
              {m.label}
            </button>
          ))}
        </div>
      )}
      {vizStyle === 'galaxy' && (
        <div className="map-pill-group">
          {GALAXY_MODES.map((m) => (
            <button key={m.id} type="button" className={`map-pill${galaxyMode === m.id ? ' active' : ''}`} onClick={() => setGalaxyMode(m.id)} aria-pressed={galaxyMode === m.id}>
              {m.label}
            </button>
          ))}
        </div>
      )}
      <div className="map-pill-group">
        {VIZ_STYLES.map((s) => (
          <button key={s.id} type="button" className={`map-pill${vizStyle === s.id ? ' active' : ''}${!s.enabled ? ' disabled' : ''}`} onClick={() => s.enabled && setVizStyle(s.id)} title={!s.enabled ? 'Coming soon' : ''} aria-pressed={vizStyle === s.id}>
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
  const appIsDark = useThemeIsDark();
  const { vizStyle, viewMode, galaxyMode, setGalaxyMode } = vizState;
  const { node, fullTree, currentPath, onPathChange } = treeState;
  const { onDrillDown, onFileClick, onNavigate, onBreadcrumbNav } = callbacks;
  const { showLabels, setShowLabels, darkMode, setDarkMode, breadcrumb, resetKey, projectName, standardTypes } = display;
  return (
    <div className="map-viz-container" {...(darkMode && !appIsDark ? { 'data-theme': getDarkThemeAttr() } : {})}>
      {vizStyle !== 'galaxy' && <MapBreadcrumb path={breadcrumb} onNavigate={onBreadcrumbNav} projectName={projectName} />}
      <div className="map-viz-toggles">
        <label className="map-label-toggle">
          <input type="checkbox" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)} />
          Labels
        </label>
        {!appIsDark && (
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

function MapEmpty({ sub, children }) {
  return (
    <div className="map-page map-page--terminal">
      <TermHeader name="map" sub={sub} />
      {children}
    </div>
  );
}

export default function MapPage(props) {
  const { data = {}, callbacks = {} } = props;
  const { projects = [], projectsLoaded, selectedProject, selectedSource = 'local', projectName, loading, isFetching } = data;
  const { onNavigate } = callbacks;

  // Call the hook unconditionally to keep hook order stable across renders.
  // The hook tolerates missing data — `state.allDimensions` is `[]` when there
  // is no project or no run data, which is exactly what we use for case C.
  const state = useMapPageState(props);

  if (!projectsLoaded) return <LoadingScreen />;
  if (projects.length === 0) {
    return (
      <MapEmpty sub="no projects yet">
        <EmptyState
          title="No projects yet"
          description="Add a project to start analyzing code quality."
          actionLabel="Add a project"
          onAction={() => onNavigate?.('projects')}
        />
      </MapEmpty>
    );
  }
  if (!selectedProject) {
    return (
      <MapEmpty sub="no project selected">
        <EmptyState
          title="No project selected"
          description="Pick a project to view its map."
          actionLabel="Choose project"
          onAction={() => onNavigate?.('projects')}
        />
      </MapEmpty>
    );
  }
  if (state.allDimensions.length === 0) {
    if (loading || isFetching) return <LoadingScreen />;
    // Shared projects are read-only in the app -- evaluations only ever run
    // locally, so "Start evaluation" has nowhere useful to send a
    // shared-project viewer (see DashboardPage's NoCompletedEvalPanel, the
    // precedent this mirrors).
    if (selectedSource === 'shared') {
      return (
        <MapEmpty sub="no evaluations yet">
          <EmptyState
            title="No completed evaluation yet"
            description="no completed evaluation in this shared project yet"
          />
        </MapEmpty>
      );
    }
    return (
      <MapEmpty sub="no evaluations yet">
        <EmptyState
          title="No evaluations yet"
          description={`Run an evaluation for ${projectName || selectedProject} to populate this page.`}
          actionLabel="Start evaluation"
          onAction={() => onNavigate?.('evaluate')}
        />
      </MapEmpty>
    );
  }

  const viol = state.currentNode.violations;
  const ratio = complianceRatio(viol, state.currentNode.compliance);

  return (
    <div className="map-page map-page--terminal">
      <div className="map-page__top">
        <TermHeader
          name="map"
          sub={`${viol} violation${viol !== 1 ? 's' : ''} · ratio ${ratio}`}
          badge={selectedSource === 'shared' ? <SharedReadOnlyBadge /> : null}
        />
        <MapControls viewState={state.viewState} galaxyState={state.galaxyState} dimensionState={state.dimensionState} />
      </div>
      <MapVizContainer vizState={state.vizState} treeState={state.treeState} dimensions={state.dimensions} callbacks={state.callbacks} display={state.display} />
    </div>
  );
}
