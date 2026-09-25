import EmptyState from '../../../components/EmptyState.jsx';
import {
  LoadProjectFailedEmptyState, NoEvalsEmptyState, NoProjectsEmptyState,
} from '../../../components/ProjectEmptyStates.jsx';
import LoadingScreen from '../../../components/LoadingScreen.jsx';
import ViolationsSkeleton from './ViolationsSkeleton.jsx';
import { TermHeader } from '../../../components/terminal/index.js';
import { t } from '../../../strings/index.js';
import { PROJECT_SOURCE } from '../../../vocab/projectSource.js';
import { NAV_TAB } from '../../../vocab/navTab.js';

function ViolationsSkeletonState() {
  return (
    <div className="violations-page violations-page--terminal">
      <TermHeader name={t('violations.termName')} sub={t('overview.loading')} />
      <ViolationsSkeleton />
    </div>
  );
}

// The "no evaluations yet" branch (loading / error / shared-no-evals /
// generic-no-evals) of the empty-state chain below.
function renderNoDimensionDataState({
  loading, error, isFetching, isRefreshing, selectedSource, projectName, selectedProject, onRetry, onNavigate,
}) {
  if (loading) return <ViolationsSkeletonState />;
  // A failed fetch with nothing to show must render as an error, not the
  // "no evaluations yet" empty state -- otherwise a 404/500/timeout tells
  // the user their existing evaluations are gone. While a retry is in
  // flight (error still set, isFetching true), show the loader instead so
  // clicking Retry visibly does something.
  if (error) {
    if (isFetching) return <ViolationsSkeletonState />;
    return (
      <div className="violations-page violations-page--terminal">
        <TermHeader name={t('violations.termName')} sub={t('violations.subError')} />
        <LoadProjectFailedEmptyState error={error} onRetry={onRetry} />
      </div>
    );
  }
  // Shared projects are read-only in the app -- evaluations only ever run
  // locally, so "Start evaluation" has nowhere useful to send a
  // shared-project viewer (see DashboardPage's NoCompletedEvalPanel, the
  // precedent this mirrors).
  if (selectedSource === PROJECT_SOURCE.SHARED) {
    return (
      <div className={`violations-page violations-page--terminal${isRefreshing ? ' dashboard-refreshing' : ''}`}>
        <TermHeader name={t('violations.termName')} sub={t('violations.subNoEvals')} />
        <EmptyState
          title={t('overview.noCompletedEvalTitle')}
          description={t('overview.noCompletedEvalSharedDesc')}
        />
      </div>
    );
  }
  return (
    <div className={`violations-page violations-page--terminal${isRefreshing ? ' dashboard-refreshing' : ''}`}>
      <TermHeader name={t('violations.termName')} sub={t('violations.subNoEvals')} />
      <NoEvalsEmptyState projectName={projectName || selectedProject} onNavigate={onNavigate} />
    </div>
  );
}

/**
 * ViolationsPage's empty-state dispatch chain (projects loading, no local
 * projects, no project selected, no dimension data); null when the page has
 * dimension data to show.
 */
export function renderViolationsEmptyState({
  projectsLoaded, projects, selectedSource, selectedProject, onNavigate,
  accumulatedDimensions, loading, isFetching, error, projectName, onRetry,
}) {
  if (!projectsLoaded) return <LoadingScreen />;
  // The LOCAL projects list can legitimately be empty while a teammate is
  // viewing a shared project (they may have never added a local project of
  // their own) -- gate this wall on the local list only for local selections,
  // so a shared selection falls through to the normal shared data flow below.
  if (projects.length === 0 && selectedSource !== PROJECT_SOURCE.SHARED) {
    return (
      <div className="violations-page violations-page--terminal">
        <TermHeader name={t('violations.termName')} sub={t('violations.subNoProjects')} />
        <NoProjectsEmptyState onNavigate={onNavigate} />
      </div>
    );
  }
  if (!selectedProject) {
    return (
      <div className="violations-page violations-page--terminal">
        <TermHeader name={t('violations.termName')} sub={t('violations.subNoProjectSelected')} />
        <EmptyState
          title={t('overview.noProjectSelectedTitle')}
          description={t('violations.noProjectSelectedDesc')}
          actionLabel={t('overview.chooseProject')}
          onAction={() => onNavigate?.(NAV_TAB.PROJECTS)}
        />
      </div>
    );
  }
  const hasAnyDimensionData = (accumulatedDimensions || []).length > 0;
  const isRefreshing = isFetching && !loading;
  if (!hasAnyDimensionData) {
    return renderNoDimensionDataState({
      loading, error, isFetching, isRefreshing, selectedSource, projectName, selectedProject, onRetry, onNavigate,
    });
  }
  return null;
}
