/**
 * Encapsulates project-level actions (delete, export, relocate) that
 * were previously inlined inside App, keeping the root component focused
 * on composition rather than API plumbing.
 */
const REQUEST_TIMEOUT_MS = 30000;

export function useProjectActions({ projects, selectedProject, handleProjectChange, loadProjects }) {
  function _apiQs() {
    const params = new URLSearchParams(window.location.search);
    const dir = params.get('evaluations') || '';
    return dir ? `?evaluations=${encodeURIComponent(dir)}` : '';
  }

  async function handleDeleteProject(projectId) {
    const qs = _apiQs();
    const separator = qs ? '&' : '?';
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}${qs}${separator}confirm=true`, { method: 'DELETE', signal: controller.signal });
    clearTimeout(timeoutId);
    if (!res.ok) {
      const msg = await res.text().catch(() => res.statusText);
      alert(`Failed to delete project: ${msg}`);
      return;
    }
    if (selectedProject === projectId) handleProjectChange(projects.find((p) => (p.id || p.name || p) !== projectId)?.id ?? '');
    loadProjects();
  }

  function handleExportProject(projectId) {
    const qs = _apiQs();
    const url = `/api/projects/${encodeURIComponent(projectId)}/export${qs}`;
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
      const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}/path${_apiQs()}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: newPath }),
      });
      if (!res.ok) {
        console.error('Relocate failed:', res.status);
        alert('Failed to relocate project. Please try again.');
        return;
      }
    } catch (err) {
      console.error('Relocate failed:', err);
      alert('Failed to relocate project. Please try again.');
      return;
    }
    loadProjects();
  }

  return { handleDeleteProject, handleExportProject, handleRelocateProject };
}
