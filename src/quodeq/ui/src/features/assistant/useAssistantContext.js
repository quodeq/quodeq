import { useAppState } from '../../hooks/useAppState.js';
import { useAssistantProvider } from '../settings/hooks/useAssistantProvider.js';

/**
 * Pure derivation of the assistant's live context from the app state and the
 * assistant provider gate. Kept side-effect-free so it can be unit-tested and
 * memoized without mounting the whole app.
 *
 * @param {Object} appState  from useAppState(): activeTab, selectedProject, selectedRun, projects,
 *                            currentOverviewRun, granularity, dailyRuns, overviewRunIndex, activePage
 * @param {Object} gate      from useAssistantProvider(): activeProvider, model
 * @returns {{ provider: string, model: string, projectId: string|undefined, runId: string|undefined, uiState: { activeTab: string, selectedProject: string, selectedRun: string, dimension?: string, grouping?: string, overviewDate?: string } }}
 */
export function deriveAssistantContext(appState, gate) {
  const {
    activeTab, selectedProject, selectedRun, projects,
    currentOverviewRun, granularity, dailyRuns, overviewRunIndex, activePage,
  } = appState || {};
  const dimension = activePage?.dimension;

  // Resolve the selected project to its canonical id/name so the session key
  // and backend runDir lookup agree with the rest of the app (which keys on
  // `p.id || p.name`). Falls back to the raw selection if the projects list
  // hasn't loaded yet, and to undefined when nothing is selected.
  const found = selectedProject && Array.isArray(projects)
    ? projects.find((p) => (p.id || p.name) === selectedProject)
    : null;
  const projectId = found ? (found.id || found.name) : (selectedProject || undefined);
  // On the overview no run is explicitly selected, but the dashboard is still
  // backing its display with one concrete run (currentOverviewRun). Bind it so
  // the backend resolves run_dir and the run-scoped tools (get_report /
  // get_scores / get_violations / search_findings) work there — the model can
  // answer principle/violation/detail questions without asking the user to
  // switch to a specific run. An explicit selection still wins.
  const runId = selectedRun || currentOverviewRun || undefined;

  // `view` names the active tab so the model can pick the right data source:
  // overview/history → accumulated (get_overview); a concrete run → run-scoped
  // tools. `selectedRun`/`currentOverviewRun` carry the concrete run when one
  // is shown so "this run" resolves correctly.
  const uiState = { view: activeTab, activeTab, selectedProject, selectedRun };
  if (currentOverviewRun) uiState.currentOverviewRun = currentOverviewRun;
  if (dimension) uiState.dimension = dimension;
  if (granularity) uiState.grouping = granularity;
  const overviewDate = Array.isArray(dailyRuns) ? dailyRuns[overviewRunIndex]?.dateLabel : undefined;
  if (overviewDate) uiState.overviewDate = overviewDate;

  return {
    provider: gate?.activeProvider,
    model: gate?.model,
    projectId,
    runId,
    uiState,
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
