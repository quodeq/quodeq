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
import { t } from '../../../strings/index.js';

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
  { id: 'zoompack', label: t('map.vizCirclePack'), enabled: true },
  { id: 'galaxy', label: 'Galaxy', enabled: true },
  { id: 'riskmatrix', label: t('map.vizRiskMatrix'), enabled: true },
];

const GALAXY_MODES = [
  { id: 'filesystem', label: t('map.vizFileSystem') },
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
        title={isFiltered ? t('map.dimensionsOf', { selected: selectedDimensions.size, total: allDimensions.length }) : t('map.allDimensions')}
        aria-label={isFiltered ? t('map.dimensionsAria', { selected: selectedDimensions.size, total: allDimensions.length }) : t('map.dimensions')}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
        </svg>
        {t('map.dimensions')}
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
          <button key={s.id} type="button" className={`map-pill${vizStyle === s.id ? ' active' : ''}${!s.enabled ? ' disabled' : ''}`} onClick={() => s.enabled && setVizStyle(s.id)} title={!s.enabled ? t('map.comingSoon') : ''} aria-pressed={vizStyle === s.id}>
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
          {t('map.labels')}
        </label>
        {!appIsDark && (
          <label className="map-label-toggle">
            <input type="checkbox" checked={!darkMode} onChange={(e) => setDarkMode(!e.target.checked)} />
            {t('map.light')}
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

function MapEmpty({ sub, children, refreshing }) {
  return (
    <div className={`map-page map-page--terminal${refreshing ? ' dashboard-refreshing' : ''}`}>
      <TermHeader name="map" sub={sub} />
      {children}
    </div>
  );
}

function MapLoadingState() {
  return (
    <MapEmpty sub="loading…">
      <LoadingScreen variant="inline" />
    </MapEmpty>
  );
}

function MapErrorState({ error, onRetry }) {
  return (
    <MapEmpty sub="error">
      <EmptyState
        title={t('map.projectLoadFailed')}
        description={error}
        actionLabel="Retry"
        onAction={() => onRetry?.()}
      />
    </MapEmpty>
  );
}

function MapNoEvaluationsState({ selectedSource, selectedProject, projectName, isRefreshing, onNavigate }) {
  // Shared projects are read-only in the app -- evaluations only ever run
  // locally, so "Start evaluation" has nowhere useful to send a
  // shared-project viewer (see DashboardPage's NoCompletedEvalPanel, the
  // precedent this mirrors).
  if (selectedSource === 'shared') {
    return (
      <MapEmpty sub={t('map.subNoEvaluations')} refreshing={isRefreshing}>
        <EmptyState
          title={t('map.noCompletedEvaluation')}
          description={t('map.noCompletedRemote')}
        />
      </MapEmpty>
    );
  }
  return (
    <MapEmpty sub={t('map.subNoEvaluations')} refreshing={isRefreshing}>
      <EmptyState
        title={t('map.noEvaluationsYet')}
        description={t('map.runEvaluationDesc', { project: projectName || selectedProject })}
        actionLabel={t('map.startEvaluation')}
        onAction={() => onNavigate?.('evaluate')}
      />
    </MapEmpty>
  );
}

// A failed fetch with nothing to show must render as an error, not the
// "no evaluations yet" empty state -- otherwise a 404/500/timeout tells
// the user their existing evaluations are gone. While a retry is in
// flight (error still set, isFetching true), show the loader instead so
// clicking Retry visibly does something.
function MapNoDimensionsState({ loading, error, isFetching, selectedSource, selectedProject, projectName, isRefreshing, onNavigate, onRetry }) {
  if (loading) return <MapLoadingState />;
  if (error) return isFetching ? <MapLoadingState /> : <MapErrorState error={error} onRetry={onRetry} />;
  return (
    <MapNoEvaluationsState
      selectedSource={selectedSource} selectedProject={selectedProject} projectName={projectName}
      isRefreshing={isRefreshing} onNavigate={onNavigate}
    />
  );
}

function MapNoProjectsState({ onNavigate }) {
  return (
    <MapEmpty sub={t('map.subNoProjects')}>
      <EmptyState
        title={t('map.noProjectsYet')}
        description={t('map.addProjectDesc')}
        actionLabel={t('map.addProject')}
        onAction={() => onNavigate?.('projects')}
      />
    </MapEmpty>
  );
}

function MapNoProjectSelectedState({ onNavigate }) {
  return (
    <MapEmpty sub={t('map.subNoProjectSelected')}>
      <EmptyState
        title={t('map.noProjectSelected')}
        description={t('map.pickProjectDesc')}
        actionLabel={t('map.chooseProject')}
        onAction={() => onNavigate?.('projects')}
      />
    </MapEmpty>
  );
}

export default function MapPage(props) {
  const { data = {}, callbacks = {} } = props;
  const { projects = [], projectsLoaded, selectedProject, selectedSource = 'local', projectName, loading, isFetching, error } = data;
  const { onNavigate, onRetry } = callbacks;

  // Call the hook unconditionally to keep hook order stable across renders.
  // The hook tolerates missing data — `state.allDimensions` is `[]` when there
  // is no project or no run data, which is exactly what we use for case C.
  const state = useMapPageState(props);

  if (!projectsLoaded) return <LoadingScreen />;
  if (projects.length === 0 && selectedSource !== 'shared') return <MapNoProjectsState onNavigate={onNavigate} />;
  if (!selectedProject) return <MapNoProjectSelectedState onNavigate={onNavigate} />;
  const isRefreshing = isFetching && !loading;
  if (state.allDimensions.length === 0) {
    return (
      <MapNoDimensionsState
        loading={loading} error={error} isFetching={isFetching} selectedSource={selectedSource}
        selectedProject={selectedProject} projectName={projectName} isRefreshing={isRefreshing}
        onNavigate={onNavigate} onRetry={onRetry}
      />
    );
  }

  const viol = state.currentNode.violations;
  const ratio = complianceRatio(viol, state.currentNode.compliance);

  return (
    <div className={`map-page map-page--terminal${isRefreshing ? ' dashboard-refreshing' : ''}`}>
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
