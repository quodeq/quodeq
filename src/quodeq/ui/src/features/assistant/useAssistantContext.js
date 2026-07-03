import { useAppState } from '../../hooks/useAppState.js';
import { useAssistantProvider } from '../settings/hooks/useAssistantProvider.js';

/**
 * Pure derivation of the assistant's live context from the app state and the
 * assistant provider gate. Kept side-effect-free so it can be unit-tested and
 * memoized without mounting the whole app.
 *
 * @param {Object} appState  from useAppState(): activeTab, selectedProject, selectedRun, projects, [dimension]
 * @param {Object} gate      from useAssistantProvider(): activeProvider, model
 * @returns {{ provider: string, model: string, projectId: string|undefined, runId: string|undefined, uiState: { activeTab: string, selectedProject: string, selectedRun: string, dimension?: string } }}
 */
export function deriveAssistantContext(appState, gate) {
  const { activeTab, selectedProject, selectedRun, projects, dimension } = appState || {};

  // Resolve the selected project to its canonical id/name so the session key
  // and backend runDir lookup agree with the rest of the app (which keys on
  // `p.id || p.name`). Falls back to the raw selection if the projects list
  // hasn't loaded yet, and to undefined when nothing is selected.
  const found = selectedProject && Array.isArray(projects)
    ? projects.find((p) => (p.id || p.name) === selectedProject)
    : null;
  const projectId = found ? (found.id || found.name) : (selectedProject || undefined);
  const runId = selectedRun || undefined;

  const uiState = { activeTab, selectedProject, selectedRun };
  if (dimension) uiState.dimension = dimension;

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
