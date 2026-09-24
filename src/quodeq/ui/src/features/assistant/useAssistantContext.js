import { useAppState } from '../../hooks/useAppState.js';
import { useAssistantProvider } from '../settings/hooks/useAssistantProvider.js';
import { PROJECT_SOURCE } from '../../vocab/projectSource.js';

/**
 * Canonical id/name for the selected project, so the session key and the
 * backend runDir lookup agree with the rest of the app (which keys on
 * `p.id || p.name`). Falls back to the raw selection while the projects list
 * has not loaded, and to undefined when nothing is selected.
 */
function resolveProjectId(selectedProject, projects) {
  const found = selectedProject && Array.isArray(projects)
    ? projects.find((p) => (p.id || p.name) === selectedProject)
    : null;
  return found ? (found.id || found.name) : (selectedProject || undefined);
}

/**
 * The UI slice the model reads to pick its data source. `view` names the
 * active tab: overview/history means the accumulated view (get_overview), a
 * concrete run means the run-scoped tools. `selectedRun` and
 * `currentOverviewRun` carry the concrete run when one is shown, so "this
 * run" resolves correctly. Optional keys are only set when they have a value,
 * so an absent one reads as absent rather than as undefined.
 */
function buildUiState(appState, dimension) {
  const {
    activeTab, selectedProject, selectedRun,
    currentOverviewRun, granularity, dailyRuns, overviewRunIndex,
  } = appState;
  const uiState = { view: activeTab, activeTab, selectedProject, selectedRun };
  if (currentOverviewRun) uiState.currentOverviewRun = currentOverviewRun;
  if (dimension) uiState.dimension = dimension;
  if (granularity) uiState.grouping = granularity;
  const overviewDate = Array.isArray(dailyRuns) ? dailyRuns[overviewRunIndex]?.dateLabel : undefined;
  if (overviewDate) uiState.overviewDate = overviewDate;
  return uiState;
}

/**
 * Pure derivation of the assistant's live context from the app state and the
 * assistant provider gate. Kept side-effect-free so it can be unit-tested and
 * memoized without mounting the whole app.
 *
 * @param {Object} appState  from useAppState(): activeTab, selectedProject, selectedRun, projects,
 *                            currentOverviewRun, granularity, dailyRuns, overviewRunIndex, activePage,
 *                            selectedSource
 * @param {Object} gate      from useAssistantProvider(): activeProvider, model
 * @returns {{ provider: string, model: string, projectId: string|undefined, runId: string|undefined, source: 'local'|'shared', uiState: { activeTab: string, selectedProject: string, selectedRun: string, dimension?: string, grouping?: string, overviewDate?: string } }}
 */
export function deriveAssistantContext(appState, gate) {
  const state = appState || {};
  const { selectedProject, selectedRun, projects, activePage, selectedSource } = state;

  return {
    provider: gate?.activeProvider,
    model: gate?.model,
    projectId: resolveProjectId(selectedProject, projects),
    // Only bind a run when the user EXPLICITLY selected one. On the overview
    // we deliberately send no runId: the session stays run-unscoped and the
    // detail tools (get_report/get_scores/get_violations) read the
    // accumulated view -- each dimension's latest run, aggregated, matching
    // the dashboard -- rather than locking to one whole run (which would show
    // stale data for dimensions whose latest run is newer). currentOverviewRun
    // still rides along in uiState so "this run" resolves, but it does not
    // scope the session.
    runId: selectedRun || undefined,
    source: selectedSource || PROJECT_SOURCE.LOCAL,
    uiState: buildUiState(state, activePage?.dimension),
  };
}

/**
 * Thin hook wrapper: reads live app state + the assistant gate and delegates
 * to the pure {@link deriveAssistantContext}. Callers that already hold an
 * app-state object (e.g. App.jsx) should call `deriveAssistantContext`
 * directly to avoid re-invoking the heavy `useAppState` hook.
 */
export function useAssistantContext() {
  const appState = useAppState();
  const gate = useAssistantProvider();
  return deriveAssistantContext(appState, gate);
}

export default useAssistantContext;
