import { useState, useEffect, useCallback } from 'react';
import { useApi } from '../api/ApiContext.jsx';

const STORAGE_KEY = 'quodeq_selected_project';
const DEFAULT_RUN = 'latest';
const DEFAULT_MAX_RETRIES = 3;
const DEFAULT_RETRY_DELAY_MS = 400;

function persistProject(setter, name, storage = localStorage) {
  setter(name);
  try { storage.setItem(STORAGE_KEY, name); } catch { /* private browsing */ }
}

function readStoredProject(storage = localStorage) {
  try { return storage.getItem(STORAGE_KEY) || ''; } catch { return ''; }
}

/** Resolve which project to select from a loaded list, migrating stale storage if needed. */
function resolveInitialProject(list, currentProject, onChangeProject, onNoProjects, storage) {
  if (list.length === 0) {
    if (onNoProjects) onNoProjects();
    return;
  }
  const current = currentProject || readStoredProject(storage);
  const match = current && list.find((p) => (p.id || p.name) === current);
  if (!match) {
    const pick = list[0].id || list[0].name || list[0];
    onChangeProject(pick);
  }
}

/**
 * Manages the selected project, run, and project list state.
 *
 * @param {Object} params
 * @param {Function} [params.onNoProjects] - Callback invoked when the loaded project list is empty
 *   (e.g. to redirect to the evaluate tab).
 * @returns {{ projects: Array, setProjects: Function, selectedProject: string, selectedRun: string,
 *   setSelectedRun: Function, loadProjects: Function, handleProjectChange: Function,
 *   handleRunChange: Function, selectProjectAndRun: Function }}
 */
export function useProjectState({
  onNoProjects,
  storage = localStorage,
  maxRetries = DEFAULT_MAX_RETRIES,
  retryDelayMs = DEFAULT_RETRY_DELAY_MS,
}) {
  const { listProjects } = useApi();
  const [projects, setProjects] = useState([]);
  const [projectsLoaded, setProjectsLoaded] = useState(false);
  const [selectedProject, setSelectedProject] = useState(() => readStoredProject(storage));
  const [selectedRun, setSelectedRun] = useState(DEFAULT_RUN);

  // Resilient loader. A *transient* fetch failure (e.g. an aborted request
  // during a startup/reload race) must NOT be mistaken for "no projects" —
  // that used to strand the user in the onboarding wizard even though their
  // projects were fine. Retry a few times; on genuine exhaustion return null
  // so the caller skips onboarding and the app keeps its loading state (which
  // recovers on the next successful load / reconnect). A successful fetch that
  // returns an empty array is still a real "fresh user" -> onboarding.
  const loadProjects = useCallback(function load(attempt = 0) {
    return listProjects()
      .then((data) => {
        const list = Array.isArray(data) ? data : (data?.projects || []);
        setProjects(list);
        setProjectsLoaded(true);
        return list;
      })
      .catch((err) => {
        if (attempt < maxRetries) {
          return new Promise((resolve) => setTimeout(resolve, retryDelayMs))
            .then(() => load(attempt + 1));
        }
        console.warn('Failed to load projects after retries:', err);
        return null;
      });
  }, [listProjects, maxRetries, retryDelayMs]);

  useEffect(() => {
    loadProjects().then((list) => {
      // Array (possibly empty -> onboarding) on success; null when the load
      // failed after retries -> do NOT force onboarding on a transient error.
      if (list) resolveInitialProject(list, selectedProject, handleProjectChange, onNoProjects, storage);
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function handleProjectChange(name) {
    persistProject(setSelectedProject, name, storage);
    setSelectedRun(DEFAULT_RUN);
  }

  function handleRunChange(runId) { setSelectedRun(runId); }

  function selectProjectAndRun(project, runId) {
    persistProject(setSelectedProject, project, storage);
    setSelectedRun(runId || DEFAULT_RUN);
  }

  return {
    projects,
    projectsLoaded,
    setProjects,
    selectedProject,
    selectedRun,
    setSelectedRun,
    loadProjects,
    handleProjectChange,
    handleRunChange,
    selectProjectAndRun,
  };
}
