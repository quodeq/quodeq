import EmptyState from '../../../components/EmptyState.jsx';
import LoadingScreen from '../../../components/LoadingScreen.jsx';
import { TermHeader } from '../../../components/terminal/index.js';
import { t } from '../../../strings/index.js';
import { PROJECT_SOURCE } from '../../../vocab/projectSource.js';
import { NAV_TAB } from '../../../vocab/navTab.js';

// Framed Map states: every one keeps the `map` TermHeader so the tab never
// blanks out while loading, failing, or waiting for a project.

export function MapEmpty({ sub, children, refreshing }) {
  return (
    <div className={`map-page map-page--terminal${refreshing ? ' section-pending' : ''}`}>
      <TermHeader name="map" sub={sub} />
      {children}
    </div>
  );
}

export function MapLoadingState() {
  return (
    <MapEmpty sub={t('overview.loading')}>
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
  if (selectedSource === PROJECT_SOURCE.SHARED) {
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
        onAction={() => onNavigate?.(NAV_TAB.EVALUATE)}
      />
    </MapEmpty>
  );
}

// A failed fetch with nothing to show must render as an error, not the
// "no evaluations yet" empty state -- otherwise a 404/500/timeout tells
// the user their existing evaluations are gone. While a retry is in
// flight (error still set, isFetching true), show the loader instead so
// clicking Retry visibly does something.
export function MapNoDimensionsState({ loading, error, isFetching, selectedSource, selectedProject, projectName, isRefreshing, onNavigate, onRetry }) {
  if (loading) return <MapLoadingState />;
  if (error) return isFetching ? <MapLoadingState /> : <MapErrorState error={error} onRetry={onRetry} />;
  return (
    <MapNoEvaluationsState
      selectedSource={selectedSource} selectedProject={selectedProject} projectName={projectName}
      isRefreshing={isRefreshing} onNavigate={onNavigate}
    />
  );
}

export function MapNoProjectsState({ onNavigate }) {
  return (
    <MapEmpty sub={t('map.subNoProjects')}>
      <EmptyState
        title={t('map.noProjectsYet')}
        description={t('map.addProjectDesc')}
        actionLabel={t('map.addProject')}
        onAction={() => onNavigate?.(NAV_TAB.PROJECTS)}
      />
    </MapEmpty>
  );
}

export function MapNoProjectSelectedState({ onNavigate }) {
  return (
    <MapEmpty sub={t('map.subNoProjectSelected')}>
      <EmptyState
        title={t('map.noProjectSelected')}
        description={t('map.pickProjectDesc')}
        actionLabel={t('map.chooseProject')}
        onAction={() => onNavigate?.(NAV_TAB.PROJECTS)}
      />
    </MapEmpty>
  );
}
