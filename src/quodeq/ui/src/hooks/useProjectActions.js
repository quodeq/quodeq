/**
 * Encapsulates project-level actions (delete, export, relocate) that
 * were previously inlined inside App, keeping the root component focused
 * on composition rather than API plumbing.
 */
import { useApi } from '../api/ApiContext.jsx';

export function useProjectActions({ projects, selectedProject, handleProjectChange, loadProjects }) {
  const { deleteProject, getProjectExportUrl, relocateProject } = useApi();
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
    const proj = projects.find((p) => (p.id || p.name) === projectId);
    const filename = `${proj?.name || projectId}.zip`;
    // PyWebView: native Save dialog, fetches server-side
    if (window.pywebview?.api?.download_url) {
      window.pywebview.api.download_url(`/api/projects/${encodeURIComponent(projectId)}/export`, filename);
      return;
    }
    // Regular browser: <a download> works
    const url = getProjectExportUrl(projectId);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  async function handleRelocateProject(projectId, newPath) {
    try {
      await relocateProject(projectId, newPath);
    } catch (err) {
      console.error('Relocate failed:', err);
      alert(`Failed to relocate project: ${err.message || 'unknown error'}. Check that the target path is writable and try again.`);
      return;
    }
    loadProjects();
  }

  return { handleDeleteProject, handleExportProject, handleRelocateProject };
}
