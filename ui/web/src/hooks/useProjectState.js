import { useState, useEffect, useCallback } from 'react';
import { listProjects } from '../api/index.js';

export function useProjectState({ onNoProjects }) {
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(() => {
    try { return localStorage.getItem('quodeq_selected_project') || ''; } catch { return ''; }
  });
  const [selectedRun, setSelectedRun] = useState('latest');

  const loadProjects = useCallback(() => {
    return listProjects()
      .then((data) => {
        const list = Array.isArray(data) ? data : (data?.projects || []);
        setProjects(list);
        return list;
      })
      .catch(() => []);
  }, []);

  useEffect(() => {
    loadProjects().then((list) => {
      if (list.length > 0) {
        const current = selectedProject || localStorage.getItem('quodeq_selected_project') || '';
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
    setSelectedProject(name);
    try { localStorage.setItem('quodeq_selected_project', name); } catch { /* private browsing */ }
    setSelectedRun('latest');
  }

  function handleRunChange(runId) { setSelectedRun(runId); }

  function selectProjectAndRun(project, runId) {
    setSelectedProject(project);
    try { localStorage.setItem('quodeq_selected_project', project); } catch { /* private browsing */ }
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
