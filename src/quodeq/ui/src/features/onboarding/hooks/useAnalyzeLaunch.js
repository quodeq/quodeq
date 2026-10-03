import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { useCloneStatus } from '../../../hooks/useCloneStatus.js';
import { HTTP_STATUS } from '../../../constants.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';
import { t } from '../../../strings/index.js';
import { REPO_SOURCE } from '../onboardingVocab.js';
import { makeTryResumeExisting, resumedExisting } from './resumeExisting.js';
import { startFolder, startUrl } from './analyzeLaunchStart.js';

// The clone slot's code for a repo the server already holds; `detail` is its id.
const CODE_PROJECT_EXISTS = 'PROJECT_EXISTS';

// A clone that failed: resume and run the existing project on PROJECT_EXISTS
// (when it has no evaluations yet), otherwise the mapped message and git's output.
async function landFailure(slot, latest, setters) {
  const { tryResume, form, launch } = latest.current;
  const exists = slot.code === CODE_PROJECT_EXISTS;
  if (exists && slot.detail) {
    const conflict = { status: HTTP_STATUS.CONFLICT, existingProjectId: slot.detail };
    if (await resumedExisting(conflict, tryResume)) {
      await launch({ projectId: slot.detail, repo: slot.repo, standardIds: form.request().standardIds });
      return;
    }
  }
  // PROJECT_EXISTS carries a project id in `detail`, not git output: never shown.
  const detail = exists ? '' : (slot.detail || '');
  setters.setCloneError({ message: apiErrorMessage({ code: slot.code, message: slot.error }, 'onboarding.cloneFailed'), detail });
}

// POST /api/evaluations takes a local path, never a url: a cloned project
// launches its working copy, the registered project's path. When the project
// cannot be read the repo goes as it is and the start reports the refusal.
async function localRepo(api, { projectId, repo }) {
  if (!projectId) return repo;
  try {
    const info = await api.getProjectInfo(projectId);
    return info?.path || repo;
  } catch (err) {
    console.warn('[useAnalyzeLaunch] could not read the launched project, sending its repo as is:', err);
    return repo;
  }
}

/**
 * Acts once on the terminal edge of the clone this panel follows: the slot is
 * for `pending.repo` and its finishedAt is new (not the one cached before the
 * post, not one already handled). DONE launches; ERROR shows or resumes;
 * another repository's clone finishing (a 409 attach) lets this one start.
 */
function useCloneLanding({ clone, pending, setPending, latest, setters }) {
  const handled = useRef(null);
  useEffect(() => {
    const { slot } = clone;
    if (!pending || !slot || slot.repo !== pending.repo || !(clone.done || clone.failed)) return;
    if (slot.finishedAt === pending.stale || slot.finishedAt === handled.current) return;
    handled.current = slot.finishedAt;
    if (pending.requested && pending.requested !== pending.repo) {
      setPending(null);
      latest.current.run().catch((err) => console.warn('[useAnalyzeLaunch] starting after the other clone failed:', err));
      return;
    }
    if (clone.done) {
      const { wizard, form, launch } = latest.current;
      wizard.succeedScan(slot.projectId, slot.scanData ?? null);
      // The repo that landed, not the field (which a reopened panel may hold differently).
      launch({ projectId: slot.projectId, repo: slot.repo, standardIds: form.request().standardIds })
        .catch((err) => console.warn('[useAnalyzeLaunch] launching the cloned project failed:', err));
      return;
    }
    setPending(null);
    landFailure(slot, latest, setters).catch((err) => console.warn('[useAnalyzeLaunch] clone failure handling failed:', err));
    // Keyed on the slot and pending alone: callbacks are read through `latest`.
  }, [pending, clone.slot]);
}

/**
 * Reopening the panel while a clone runs follows it (no `scan and run`
 * needed); an empty repository field shows the url being cloned.
 */
function useAttachToActive({ clone, pending, setPending, startingRef, latest }) {
  useEffect(() => {
    if (!clone.active || pending || startingRef.current) return;
    setPending({ repo: clone.slot.repo, requested: null, stale: null, conflict: false });
    const { wizard, form } = latest.current;
    if (!form.request().repo) wizard.setRepo({ source: REPO_SOURCE.URL, value: clone.slot.repo });
    // The refs are read current; the slot and pending decide.
  }, [clone.active, clone.slot, pending]);
}

/**
 * A followed clone that vanished (seen running for pending.repo, now idle or
 * another repo's, e.g. the server restarted mid-clone) ends the follow with
 * an error instead of leaving the panel busy forever.
 */
function useLostFollow({ clone, pending, setters }) {
  const seen = useRef(null);
  useEffect(() => {
    const { slot } = clone;
    if (!pending) { seen.current = null; return; }
    const ours = slot?.repo === pending.repo;
    if (clone.active && ours) { seen.current = pending; return; }
    if (seen.current !== pending || (ours && (clone.done || clone.failed))) return;
    seen.current = null;
    setters.setPending(null);
    setters.setStartError({ message: t('onboarding.cloneFailed'), detail: '' });
  }, [pending, clone.slot]);
}

function useLaunchState() {
  const [pending, setPending] = useState(null);
  const [accessFailure, setAccessFailure] = useState(null);
  const [startError, setStartError] = useState(null);
  const [cloneError, setCloneError] = useState(null);
  const [starting, setStarting] = useState(false);
  return {
    pending, accessFailure, startError, cloneError, starting,
    setters: { setPending, setAccessFailure, setStartError, setCloneError, setStarting },
  };
}

/**
 * `scan and run`. A folder registers synchronously and launches at once. A
 * url is probed (unreachable opens the access panel), posted as a clone job
 * (202), and followed through the shared clone slot: the evaluation starts
 * exactly once when that slot reaches DONE for this repo. A 409
 * CLONE_IN_PROGRESS follows the running clone instead of failing.
 * PROJECT_EXISTS resumes the registered project and launches it at once.
 * Closing the panel (unmount) drops `pending`: nothing is
 * cancelled and nothing launches later.
 *
 * `onLaunch({ projectId, repo, standardIds })` starts the evaluation with the
 * project's local path as `repo`; never after the panel unmounted.
 *
 * @param {{ wizard: object, form: { request: () => object }, onLaunch: Function }} args
 */
export function useAnalyzeLaunch({ wizard, form, onLaunch }) {
  const api = useApi();
  const queryClient = useQueryClient();
  const clone = useCloneStatus();
  const s = useLaunchState();
  const { setters } = s;
  const startingRef = useRef(false);
  const latest = useRef(null);
  // Closing the panel unmounts it: a launch that resolves after that (a slow
  // registration or resume) must not open the evaluation.
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  const launch = async (args) => {
    const repo = await localRepo(api, args);
    if (mounted.current) latest.current.onLaunch({ ...args, repo });
  };

  async function run() {
    if (startingRef.current) return;
    const request = form.request();
    startingRef.current = true;
    setters.setStarting(true);
    setters.setAccessFailure(null); setters.setStartError(null); setters.setCloneError(null);
    const ctx = {
      api, queryClient, wizard, set: setters, slot: () => latest.current.clone.slot, tryResume: latest.current.tryResume, launch,
    };
    try {
      await (request.source === REPO_SOURCE.FOLDER ? startFolder(ctx, request) : startUrl(ctx, request));
    } finally {
      startingRef.current = false;
      setters.setStarting(false);
    }
  }

  const tryResume = makeTryResumeExisting({ getProjectInfo: api.getProjectInfo, getProjectScan: api.getProjectScan, actions: wizard });
  latest.current = { wizard, form, onLaunch, launch, run, tryResume, clone };
  useCloneLanding({ clone, pending: s.pending, setPending: setters.setPending, latest, setters });
  useAttachToActive({ clone, pending: s.pending, setPending: setters.setPending, startingRef, latest });
  useLostFollow({ clone, pending: s.pending, setters });

  const followed = s.pending && clone.active && clone.slot.repo === s.pending.repo ? clone.slot : null;
  const withRetry = (error) => (error ? { ...error, retry: run } : null);
  return {
    run,
    busy: s.starting || Boolean(s.pending),
    pending: Boolean(s.pending),
    slot: followed,
    phase: followed?.phase ?? null,
    attachedElsewhere: Boolean(s.pending?.conflict),
    accessFailure: s.accessFailure,
    startError: withRetry(s.startError),
    cloneError: withRetry(s.cloneError),
  };
}
