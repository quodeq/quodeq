/**
 * The dashboard data bundle handed to every DashboardPage route.
 *
 * Same hazard as buildNavigationBundle (see navigationBundle.js), quieter
 * failure: this is an explicit key whitelist, so a field added to
 * useAppState and read by DashboardPage silently arrives as undefined
 * unless it is forwarded here. Nothing throws -- the feature just never
 * activates (that is how scoresPending, and the dimension-panel pending
 * state that depends on it, was inert at first). Exported so producer and
 * consumer can be pinned together in tests.
 *
 * Moved out of routes/renderers.jsx verbatim (move-only refactor).
 */
export function buildDashboardDataBundle({ state, sharedHasContent = false }) {
  return {
    selectedProject: state.selectedProject, selectedSource: state.selectedSource, selectedRun: state.selectedRun, projects: state.projects,
    projectsLoaded: state.projectsLoaded,
    projectsLoadFailed: state.projectsLoadFailed,
    onProjectsRetry: state.retryLoadProjects,
    warmup: state.warmup,
    dashboard: state.dashboard, accumulated: state.accumulated, latestAccumulated: state.latestAccumulated, loading: state.loading, isFetching: state.isFetching, error: state.error,
    onRetry: state.refreshDashboardActive,
    scoresPending: state.scoresPending,
    sharedProjectInfo: state.sharedProjectInfo,
    availableRuns: state.availableRuns, dailyRuns: state.dailyRuns, overviewRunIndex: state.overviewRunIndex,
    selectedDisplayName: state.selectedDisplayName,
    granularity: state.granularity, onGranularityChange: state.onGranularityChange,
    sharedHasContent,
  };
}
