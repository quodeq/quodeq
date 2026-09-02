import { useState } from 'react';
import { getProjectScan as apiGetProjectScan } from '../../../api/index.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';

const URL_RE = /^(https?:\/\/|git@|ssh:\/\/|git:\/\/)/i;
const CLONE_DEST_STORAGE_KEY = 'quodeq.lastCloneRoot';

// Map backend error codes (Task A8) to user-facing messages. The switch that
// used to live here moved into strings/apiErrors.js so every screen resolves
// codes the same way; the copy is unchanged, just translatable now.
function friendlyCloneError(err) {
  return apiErrorMessage(err, 'onboarding.cloneFailed');
}

/**
 * RepoScanStep.jsx's scan/clone submission state and handlers (including the
 * 409-resume flow), extracted verbatim.
 */
export function useRepoScanStep({ state, actions, createProject, getProjectInfo, getProjectScan = apiGetProjectScan }) {
  const [folderBrowserOpen, setFolderBrowserOpen] = useState(false);
  const [subStep, setSubStep] = useState('input'); // 'input' | 'cloneTarget'
  const [cloneSubmitting, setCloneSubmitting] = useState(false);
  const [cloneError, setCloneError] = useState(null);

  // 409 + existingProjectId means a project was already registered for this
  // repo. If it has no evaluations yet, silently resume into it — the user
  // most likely abandoned an earlier onboarding attempt. If it does have
  // evaluations, fall through to the normal error UI so the user can decide.
  async function tryResumeExisting(existingProjectId) {
    try {
      const info = await getProjectInfo(existingProjectId);
      if (info.runsCount > 0) return false;
      // Timeout so a backend that accepts but never responds cannot stall
      // the resume flow; the catch below falls back to the normal error UI
      // (the adapter rejects on non-2xx too, landing in the same catch).
      // The explicit `timeout` lifts the adapter's 30s default to match.
      const scanData = await getProjectScan(existingProjectId, {
        signal: AbortSignal.timeout(120000),
        timeout: 120000,
      });
      actions.succeedScan(existingProjectId, scanData);
      return true;
    } catch {
      return false;
    }
  }

  async function handleSubmit() {
    const repo = state.repo.value?.trim();
    if (!repo) return;
    if (URL_RE.test(repo)) {
      // URL input branches into the clone-target sub-step. Local-path inputs
      // continue to call createProject directly.
      setSubStep('cloneTarget');
      setCloneError(null);
      return;
    }
    actions.startScan();
    try {
      const { projectId, scanData } = await createProject({ repo });
      actions.succeedScan(projectId, scanData);
    } catch (err) {
      if (err.status === 409 && err.existingProjectId) {
        const resumed = await tryResumeExisting(err.existingProjectId);
        if (resumed) return;
      }
      actions.failScan({ message: err.message, status: err.status, existingProjectId: err.existingProjectId });
    }
  }

  async function handleCloneTargetSubmit({ cloneDest, ephemeral }) {
    const repo = state.repo.value?.trim();
    setCloneSubmitting(true);
    setCloneError(null);
    actions.startScan();
    try {
      const payload = { repo, cloneDest, ephemeral };
      const { projectId, scanData } = await createProject(payload);
      if (cloneDest && !ephemeral) {
        try { localStorage.setItem(CLONE_DEST_STORAGE_KEY, cloneDest); } catch (_) { /* private mode */ }
      }
      actions.succeedScan(projectId, scanData);
      setSubStep('input');
    } catch (err) {
      if (err.status === 409 && err.existingProjectId) {
        const resumed = await tryResumeExisting(err.existingProjectId);
        if (resumed) {
          setSubStep('input');
          return;
        }
      }
      setCloneError(friendlyCloneError(err));
      actions.failScan({ message: err.message, status: err.status, existingProjectId: err.existingProjectId, code: err.code });
    } finally {
      setCloneSubmitting(false);
    }
  }

  function handleFolderSelect(path) {
    actions.setRepo({ value: path, source: 'local' });
    setFolderBrowserOpen(false);
  }

  return {
    folderBrowserOpen, setFolderBrowserOpen,
    subStep, setSubStep,
    cloneSubmitting, cloneError, setCloneError,
    handleSubmit, handleCloneTargetSubmit, handleFolderSelect,
  };
}
