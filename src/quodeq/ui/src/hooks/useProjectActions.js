/**
 * Encapsulates project-level actions (delete, export, relocate, import) that
 * were previously inlined inside App, keeping the root component focused
 * on composition rather than API plumbing.
 */
import { useApi } from '../api/ApiContext.jsx';
import { chooseDialog } from '../utils/chooseDialog.js';

// Strip filesystem-unfriendly characters so a project name like
// "foo/bar" or "..\\evil" can't influence the download path.
function sanitizeFilename(name) {
  return String(name || '')
    .replace(/[/\\:*?"<>|\x00-\x1f]+/g, '_')
    .replace(/^\.+/, '_')
    .slice(0, 100) || 'project';
}

export function useProjectActions({ projects, selectedProject, handleProjectChange, loadProjects }) {
  const { deleteProject, getProjectExportUrl, relocateProject, importProject } = useApi();
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
    const filename = `${sanitizeFilename(proj?.name || projectId)}.zip`;
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

  async function _attemptImport(file, action) {
    try {
      return { ok: true, result: await importProject(file, action ? { action } : {}) };
    } catch (err) {
      return { ok: false, err };
    }
  }

  async function _resolveImportConflict(file, err) {
    const isSameUuid = err.kind === 'same_uuid';
    const projectLabel = err.projectName ? ` "${err.projectName}"` : '';
    const message = isSameUuid
      ? `A project${projectLabel} with this ID already exists. Replace it, import as a separate copy, or cancel.`
      : `A project${projectLabel} for this repository already exists. Import as a separate copy or cancel.`;
    // When Replace is offered alongside Copy, render Copy as a neutral
    // outline button so the destructive Replace is the only red one. When
    // Copy is the sole action (same_identity), keep it emphasized.
    const actions = isSameUuid
      ? [
          { key: 'copy', label: 'Import as copy', variant: 'default' },
          { key: 'replace', label: 'Replace', variant: 'danger' },
        ]
      : [{ key: 'copy', label: 'Import as copy', variant: 'primary' }];
    const choice = await chooseDialog({
      title: 'Project already exists',
      message,
      actions,
    });
    if (!choice) return null;
    return _attemptImport(file, choice);
  }

  async function handleImportProject() {
    if (typeof document === 'undefined') return;
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.zip,application/zip,application/x-zip-compressed';
    input.style.display = 'none';
    document.body.appendChild(input);
    const file = await new Promise((resolve) => {
      input.addEventListener('change', () => resolve(input.files?.[0] || null), { once: true });
      input.addEventListener('cancel', () => resolve(null), { once: true });
      input.click();
    });
    document.body.removeChild(input);
    if (!file) return;

    let attempt = await _attemptImport(file);
    if (!attempt.ok && attempt.err.status === 409 && attempt.err.kind) {
      attempt = await _resolveImportConflict(file, attempt.err);
      if (attempt === null) return; // user cancelled
    }
    if (!attempt.ok) {
      alert(`Failed to import project: ${attempt.err.message || 'unknown error'}`);
      return;
    }
    loadProjects();
  }

  return { handleDeleteProject, handleExportProject, handleRelocateProject, handleImportProject };
}
