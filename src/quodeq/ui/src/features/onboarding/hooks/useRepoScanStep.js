import { useRef, useState } from 'react';
import { getProjectScan as apiGetProjectScan, probeGit as apiProbeGit } from '../../../api/index.js';
import { apiErrorMessage, apiErrorDetail, isAccessCode } from '../../../strings/apiErrors.js';
import { writeString } from '../../../adapters/storage.js';
import { LAST_CLONE_ROOT_STORAGE_KEY, HTTP_STATUS } from '../../../constants.js';

// RepoScanStep's own sub-step: the repo-url input form, or the clone-target
// picker (once a remote URL needs a local destination).
export const REPO_SCAN_SUB_STEP = Object.freeze({ INPUT: 'input', CLONE_TARGET: 'cloneTarget' });

const URL_RE = /^(https?:\/\/|git@|ssh:\/\/)/i;
// Lifts the adapter's 30s default so a resume scan (which reads a project
// that may not have finished its first scan yet) isn't cut short.
const RESUME_SCAN_TIMEOUT_MS = 120000;

// Map backend error codes to user-facing messages. The switch that
// used to live here moved into strings/apiErrors.js so every screen resolves
// codes the same way; the copy is unchanged, just translatable now.
function friendlyCloneError(err) {
  return apiErrorMessage(err, 'onboarding.cloneFailed');
}

// 409 + existingProjectId means a project was already registered for this
// repo. If it has no evaluations yet, silently resume into it — the user
// most likely abandoned an earlier onboarding attempt. If it does have
// evaluations, fall through to the normal error UI so the user can decide.
function makeTryResumeExisting({ getProjectInfo, getProjectScan, actions }) {
  return async function tryResumeExisting(existingProjectId) {
    try {
      const info = await getProjectInfo(existingProjectId);
      if (info.runsCount > 0) return false;
      // Timeout so a backend that accepts but never responds cannot stall
      // the resume flow; the catch below falls back to the normal error UI
      // (the adapter rejects on non-2xx too, landing in the same catch).
      // The explicit `timeout` lifts the adapter's 30s default to match.
      const scanData = await getProjectScan(existingProjectId, {
        signal: AbortSignal.timeout(RESUME_SCAN_TIMEOUT_MS),
        timeout: RESUME_SCAN_TIMEOUT_MS,
      });
      actions.succeedScan(existingProjectId, scanData);
      return true;
    } catch (err) {
      console.warn('[useRepoScanStep] resume existing project failed:', err);
      return false;
    }
  };
}

// A repo that is already registered comes back as a 409 carrying the
// existing project id: resuming it is the right answer, not a failure.
async function resumedExisting(err, tryResumeExisting) {
  if (err.status !== HTTP_STATUS.CONFLICT || !err.existingProjectId) return false;
  return Boolean(await tryResumeExisting(err.existingProjectId));
}

/**
 * Builds the Repo & Scan submit handler. A URL branches into the clone-target
 * sub-step; a local path creates the project straight away. When the backend
 * reports the repo is already registered (409), the existing project is
 * resumed instead of failing.
 */
export function makeHandleSubmit({ state, actions, createProject, setSubStep, setCloneError, tryResumeExisting }) {
  return async function handleSubmit() {
    const repo = state.repo.value?.trim();
    if (!repo) return;
    if (URL_RE.test(repo)) {
      // URL input branches into the clone-target sub-step. Local-path inputs
      // continue to call createProject directly.
      setSubStep(REPO_SCAN_SUB_STEP.CLONE_TARGET);
      setCloneError(null);
      return;
    }
    actions.startScan();
    try {
      const { projectId, scanData } = await createProject({ repo });
      actions.succeedScan(projectId, scanData);
    } catch (err) {
      if (await resumedExisting(err, tryResumeExisting)) return;
      actions.failScan({
        message: apiErrorMessage(err, 'onboarding.scanFailed'),
        status: err.status,
        existingProjectId: err.existingProjectId,
      });
    }
  };
}

function accessFailureFrom(err) {
  const b = err?.body || {};
  return { kind: b.kind, detail: b.detail || '', host: b.host || '', isGitHub: Boolean(b.isGitHub) };
}

/**
 * Builds the clone-target submit handler. Probes the URL first: an unreachable
 * verdict opens the access panel instead of starting a clone that cannot
 * succeed. A reachable one clones into the chosen destination and scans. The
 * last submit is remembered so the panel can retry it once access is fixed.
 */
export function makeHandleCloneTargetSubmit({ state, actions, createProject, probeGit, setSubStep, setCloneError, setCloneDetail, setCloneSubmitting, setAccessFailure, lastSubmitRef, tryResumeExisting }) {
  return async function handleCloneTargetSubmit({ cloneDest, ephemeral }) {
    const repo = state.repo.value?.trim();
    lastSubmitRef.current = { cloneDest, ephemeral };
    setCloneSubmitting(true);
    setCloneError(null);
    setCloneDetail('');
    setAccessFailure(null);
    try {
      const access = await probeGit(repo);
      if (!access.reachable) {
        setAccessFailure({ kind: access.kind, detail: access.detail || '', host: access.host || '', isGitHub: Boolean(access.isGitHub) });
        return;
      }
      actions.startScan();
      const { projectId, scanData } = await createProject({ repo, cloneDest, ephemeral });
      if (cloneDest && !ephemeral) {
        const ok = writeString(LAST_CLONE_ROOT_STORAGE_KEY, cloneDest);
        if (!ok) console.warn('[useRepoScanStep] could not persist clone destination'); // private mode
      }
      actions.succeedScan(projectId, scanData);
      setSubStep(REPO_SCAN_SUB_STEP.INPUT);
    } catch (err) {
      if (await resumedExisting(err, tryResumeExisting)) {
        setSubStep(REPO_SCAN_SUB_STEP.INPUT);
        return;
      }
      if (isAccessCode(err.code)) {
        setAccessFailure(accessFailureFrom(err));
        actions.resetScan();
        return;
      }
      const message = friendlyCloneError(err);
      setCloneError(message);
      setCloneDetail(apiErrorDetail(err));
      actions.failScan({ message, status: err.status, existingProjectId: err.existingProjectId, code: err.code });
    } finally {
      setCloneSubmitting(false);
    }
  };
}

/**
 * The Repo & Scan step's state and handlers: the folder browser, the
 * input/clone-target sub-step, and the two submit paths.
 *
 * `getProjectScan` is injectable for tests.
 */
export function useRepoScanStep({ state, actions, createProject, getProjectInfo, getProjectScan = apiGetProjectScan, probeGit = apiProbeGit }) {
  const [folderBrowserOpen, setFolderBrowserOpen] = useState(false);
  const [subStep, setSubStep] = useState(REPO_SCAN_SUB_STEP.INPUT);
  const [cloneSubmitting, setCloneSubmitting] = useState(false);
  const [cloneError, setCloneError] = useState(null);
  const [cloneDetail, setCloneDetail] = useState('');
  const [accessFailure, setAccessFailure] = useState(null);
  const lastSubmitRef = useRef(null);

  const tryResumeExisting = makeTryResumeExisting({ getProjectInfo, getProjectScan, actions });
  const handleSubmit = makeHandleSubmit({ state, actions, createProject, setSubStep, setCloneError, tryResumeExisting });
  const handleCloneTargetSubmit = makeHandleCloneTargetSubmit({
    state, actions, createProject, probeGit, setSubStep, setCloneError, setCloneDetail, setCloneSubmitting,
    setAccessFailure, lastSubmitRef, tryResumeExisting,
  });

  function handleFolderSelect(path) {
    actions.setRepo({ value: path, source: 'local' });
    setFolderBrowserOpen(false);
  }

  function clearAccessFailure() { setAccessFailure(null); }
  function retryClone() {
    return lastSubmitRef.current ? handleCloneTargetSubmit(lastSubmitRef.current) : Promise.resolve();
  }

  return {
    folderBrowserOpen, setFolderBrowserOpen,
    subStep, setSubStep,
    cloneSubmitting, cloneError, setCloneError, cloneDetail,
    accessFailure, clearAccessFailure, retryClone,
    handleSubmit, handleCloneTargetSubmit, handleFolderSelect,
  };
}
