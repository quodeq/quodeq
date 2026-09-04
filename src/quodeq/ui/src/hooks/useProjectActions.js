/**
 * Encapsulates project-level actions (delete, export, relocate, import) that
 * were previously inlined inside App, keeping the root component focused
 * on composition rather than API plumbing.
 *
 * Failure handlers return `{ ok: false, messageKey, vars }` (the raw i18n
 * key + interpolation vars, not a rendered string) so a caller can inspect
 * or relocalize the failure; success returns `{ ok: true }`. Separately,
 * *onError* (optional second-arg option) is invoked with the RENDERED
 * message (`t(messageKey, vars)`) so a caller that just wants the old
 * "tell the user" behavior doesn't have to render it itself -- defaults to
 * a no-op, since failures already surface structurally via the returned
 * `{ ok: false, messageKey, vars }` and a caller owns how (or whether) to
 * present them.
 */
import { useApi } from '../api/ApiContext.jsx';
import { chooseDialog } from '../utils/chooseDialog.js';
import { t } from '../strings/index.js';
import { apiErrorMessage } from '../strings/apiErrors.js';

// Strip filesystem-unfriendly characters so a project name like
// "foo/bar" or "..\\evil" can't influence the download path.
function sanitizeFilename(name) {
  return String(name || '')
    .replace(/[/\\:*?"<>|\x00-\x1f]+/g, '_')
    .replace(/^\.+/, '_')
    .slice(0, 100) || 'project';
}

function makeFail(onError) {
  return function fail(messageKey, vars) {
    onError(messageKey, vars);
    return { ok: false, messageKey, vars };
  };
}

export function makeHandleDeleteProject({ deleteProject, projects, selectedProject, handleProjectChange, loadProjects, fail }) {
  return async function handleDeleteProject(projectId) {
    try {
      await deleteProject(projectId);
    } catch (err) {
      return fail('projects.deleteProjectFailed', { error: apiErrorMessage(err, 'projects.deleteProjectFailed') });
    }
    if (selectedProject === projectId) handleProjectChange(projects.find((p) => (p.id || p.name || p) !== projectId)?.id ?? '');
    loadProjects();
    return { ok: true };
  };
}

function makeHandleExportProject({ projects, getProjectExportUrl }) {
  return function handleExportProject(projectId) {
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
  };
}

function makeHandleRelocateProject({ relocateProject, loadProjects, fail }) {
  return async function handleRelocateProject(projectId, newPath) {
    try {
      await relocateProject(projectId, newPath);
    } catch (err) {
      console.error('Relocate failed:', err);
      return fail('projects.relocateFailed', { error: err.message || t('common.unknownError') });
    }
    loadProjects();
    return { ok: true };
  };
}

function makeAttemptImport(importProject) {
  return async function _attemptImport(file, action) {
    try {
      return { ok: true, result: await importProject(file, action ? { action } : {}) };
    } catch (err) {
      return { ok: false, err };
    }
  };
}

function makeResolveImportConflict(attemptImport) {
  return async function _resolveImportConflict(file, err) {
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
    return attemptImport(file, choice);
  };
}

async function pickImportFile() {
  if (typeof document === 'undefined') return null;
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
  return file;
}

function makeHandleImportProject({ importProject, loadProjects, fail }) {
  const attemptImport = makeAttemptImport(importProject);
  const resolveImportConflict = makeResolveImportConflict(attemptImport);
  return async function handleImportProject() {
    const file = await pickImportFile();
    if (!file) return { ok: false, cancelled: true };

    let attempt = await attemptImport(file);
    if (!attempt.ok && attempt.err.status === 409 && attempt.err.kind) {
      attempt = await resolveImportConflict(file, attempt.err);
      if (attempt === null) return { ok: false, cancelled: true }; // user cancelled
    }
    if (!attempt.ok) {
      return fail('projects.importProjectFailed', { error: attempt.err.message || t('common.unknownError') });
    }
    loadProjects();
    return { ok: true };
  };
}

export function useProjectActions(
  { projects, selectedProject, handleProjectChange, loadProjects },
  { onError = () => {} } = {},
) {
  const { deleteProject, getProjectExportUrl, relocateProject, importProject } = useApi();
  const fail = makeFail(onError);

  const handleDeleteProject = makeHandleDeleteProject({ deleteProject, projects, selectedProject, handleProjectChange, loadProjects, fail });
  const handleExportProject = makeHandleExportProject({ projects, getProjectExportUrl });
  const handleRelocateProject = makeHandleRelocateProject({ relocateProject, loadProjects, fail });
  const handleImportProject = makeHandleImportProject({ importProject, loadProjects, fail });

  return { handleDeleteProject, handleExportProject, handleRelocateProject, handleImportProject };
}
