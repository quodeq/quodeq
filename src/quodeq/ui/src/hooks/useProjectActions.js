/**
 * Encapsulates project-level actions (delete, export, relocate) that
 * were previously inlined inside App, keeping the root component focused
 * on composition rather than API plumbing.
 */
import { deleteProject, getProjectExportUrl, relocateProject } from '../api/index.js';

export function useProjectActions({ projects, selectedProject, handleProjectChange, loadProjects }) {
  async function handleDeleteProject(projectId) {
    try {
      await deleteProject(projectId);
    } catch (err) {
      alert(`Failed to delete project: ${err.message}`);
      return;
    }
    if (selectedProject === projectId) handleProjectChange(projects.find((p) => (p.id || p.name || p) !== projectId)?.id ?? '');
    loadProjects();
  }

  function handleExportProject(projectId) {
    const url = getProjectExportUrl(projectId);
    // PyWebView: open in system browser (which handles downloads)
    if (window.pywebview?.api?.open_browser) {
      window.pywebview.api.open_browser(`/api/projects/${encodeURIComponent(projectId)}/export`);
      return;
    }
    // Regular browser: <a download> works
    const proj = projects.find((p) => (p.id || p.name) === projectId);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${proj?.name || projectId}.zip`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  async function handleRelocateProject(projectId, newPath) {
    try {
      await relocateProject(projectId, newPath);
    } catch (err) {
      console.error('Relocate failed:', err);
      alert('Failed to relocate project. Please try again.');
      return;
    }
    loadProjects();
  }

  return { handleDeleteProject, handleExportProject, handleRelocateProject };
}
