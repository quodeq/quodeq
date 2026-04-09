import { useState, useEffect, useCallback } from 'react';
import { listProjects } from '../api/index.js';

const STORAGE_KEY = 'quodeq_selected_project';
const DEFAULT_RUN = 'latest';

function persistProject(setter, name) {
  setter(name);
  try { localStorage.setItem(STORAGE_KEY, name); } catch { /* private browsing */ }
}

function readStoredProject() {
  try { return localStorage.getItem(STORAGE_KEY) || ''; } catch { return ''; }
}

/** Resolve which project to select from a loaded list, migrating stale storage if needed. */
function resolveInitialProject(list, currentProject, onChangeProject, onNoProjects) {
  if (list.length === 0) {
    if (onNoProjects) onNoProjects();
    return;
  }
  const current = currentProject || readStoredProject();
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
export function useProjectState({ onNoProjects }) {
  const [projects, setProjects] = useState([]);
  const [projectsLoaded, setProjectsLoaded] = useState(false);
  const [selectedProject, setSelectedProject] = useState(readStoredProject);
  const [selectedRun, setSelectedRun] = useState(DEFAULT_RUN);

  const loadProjects = useCallback(() => {
    return listProjects()
      .then((data) => {
        const list = Array.isArray(data) ? data : (data?.projects || []);
        setProjects(list);
        setProjectsLoaded(true);
        return list;
      })
      .catch((err) => { console.warn('Failed to load projects:', err); setProjectsLoaded(true); return []; });
  }, []);

  useEffect(() => {
    loadProjects().then((list) => resolveInitialProject(list, selectedProject, handleProjectChange, onNoProjects));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function handleProjectChange(name) {
    persistProject(setSelectedProject, name);
    setSelectedRun(DEFAULT_RUN);
  }

  function handleRunChange(runId) { setSelectedRun(runId); }

  function selectProjectAndRun(project, runId) {
    persistProject(setSelectedProject, project);
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
