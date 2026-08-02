/**
 * Encapsulates project-level actions (delete, export, relocate, import) that
 * were previously inlined inside App, keeping the root component focused
 * on composition rather than API plumbing.
 */
import { useApi } from '../api/ApiContext.jsx';
import { chooseDialog } from '../utils/chooseDialog.js';
import { t } from '../strings/index.js';

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
      alert(t('projects.deleteProjectFailed', { error: err.message }));
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
      alert(t('projects.relocateFailed', { error: err.message || t('common.unknownError') }));
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
    // Four whole sentences rather than one with an optional ` "name"` spliced
    // in: the quoting style is locale-dependent (guillemets, low-high quotes)
    // and the name does not sit in the same place in every word order.
    const named = Boolean(err.projectName);
    const key = isSameUuid
      ? (named ? 'projects.conflictSameIdNamed' : 'projects.conflictSameId')
      : (named ? 'projects.conflictSameRepoNamed' : 'projects.conflictSameRepo');
    const message = t(key, { name: err.projectName });
    // When Replace is offered alongside Copy, render Copy as a neutral
    // outline button so the destructive Replace is the only red one. When
    // Copy is the sole action (same_identity), keep it emphasized.
    const actions = isSameUuid
      ? [
          { key: 'copy', label: t('projects.importAsCopy'), variant: 'default' },
          { key: 'replace', label: t('projects.replace'), variant: 'danger' },
        ]
      : [{ key: 'copy', label: t('projects.importAsCopy'), variant: 'primary' }];
    const choice = await chooseDialog({
      title: t('projects.alreadyExistsTitle'),
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
      alert(t('projects.importProjectFailed', { error: attempt.err.message || t('common.unknownError') }));
      return;
    }
    loadProjects();
  }

  return { handleDeleteProject, handleExportProject, handleRelocateProject, handleImportProject };
}
