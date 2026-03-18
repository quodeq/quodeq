import { useState, useEffect, useCallback } from 'react';
import { listProjects } from '../api/index.js';

const STORAGE_KEY = 'quodeq_selected_project';

function persistProject(setter, name) {
  setter(name);
  try { localStorage.setItem(STORAGE_KEY, name); } catch { /* private browsing */ }
}

export function useProjectState({ onNoProjects }) {
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(() => {
    try { return localStorage.getItem(STORAGE_KEY) || ''; } catch { return ''; }
  });
  const [selectedRun, setSelectedRun] = useState('latest');

  const loadProjects = useCallback(() => {
    return listProjects()
      .then((data) => {
        const list = Array.isArray(data) ? data : (data?.projects || []);
        setProjects(list);
        return list;
      })
      .catch((err) => { console.warn('Failed to load projects:', err); return []; });
  }, []);

  useEffect(() => {
    loadProjects().then((list) => {
      if (list.length > 0) {
        const current = selectedProject || localStorage.getItem(STORAGE_KEY) || '';
        const match = current && list.find((p) => (p.id || p.name) === current);
        if (!match) {
          const pick = list[0].id || list[0].name || list[0];
          handleProjectChange(pick);
        }
      } else if (list.length === 0 && onNoProjects) {
        onNoProjects();
      }
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function handleProjectChange(name) {
    persistProject(setSelectedProject, name);
    setSelectedRun('latest');
  }

  function handleRunChange(runId) { setSelectedRun(runId); }

  function selectProjectAndRun(project, runId) {
    persistProject(setSelectedProject, project);
    setSelectedRun(runId || 'latest');
  }

  return {
    projects,
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
