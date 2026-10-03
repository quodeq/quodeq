import { projectsKeys } from '../../../api/queryKeys.js';
import { isCloneActive } from '../../../api/projectClone.js';
import { apiErrorMessage, apiErrorDetail } from '../../../strings/apiErrors.js';
import { accessFailureFrom } from '../../github-access/accessFailure.js';
import { resumedExisting } from './resumeExisting.js';

// POST /api/projects refuses a second clone while one runs (the slot is shared).
const CODE_CLONE_IN_PROGRESS = 'CLONE_IN_PROGRESS';

/**
 * How `scan and run` starts, as plain async steps over a context the hook
 * builds each call:
 *   ctx.api          registerProject, probeGit, getCloneStatus
 *   ctx.queryClient  the clone slot's cache (projectsKeys.clone())
 *   ctx.wizard       startScan, succeedScan, failScan
 *   ctx.set          setPending, setAccessFailure, setStartError
 *   ctx.slot()       the clone slot as last polled
 *   ctx.tryResume    makeTryResumeExisting's resume of a registered repo
 *   ctx.launch       ({ projectId, repo, standardIds }) => void, a no-op once
 *                    the panel closed (it may run after a slow await)
 */

// A repo the server already holds (409 + existingProjectId) is resumed and
// run at once, not failed; true when it was.
async function resumed(ctx, err, { repo, standardIds }) {
  if (!(await resumedExisting(err, ctx.tryResume))) return false;
  ctx.launch({ projectId: err.existingProjectId, repo, standardIds });
  return true;
}

/**
 * A local folder registers synchronously (200 with the project and its scan)
 * and the evaluation starts at once; the clone slot is never involved.
 */
export async function startFolder(ctx, { repo, standardIds }) {
  ctx.wizard.startScan();
  try {
    const { projectId, scanData } = await ctx.api.registerProject({ repo });
    ctx.wizard.succeedScan(projectId, scanData);
    ctx.launch({ projectId, repo, standardIds });
  } catch (err) {
    if (await resumed(ctx, err, { repo, standardIds })) return;
    const message = apiErrorMessage(err, 'onboarding.scanFailed');
    ctx.wizard.failScan({ message, status: err.status, code: err.code });
    ctx.set.setStartError({ message, detail: apiErrorDetail(err) });
  }
}

// A 409 CLONE_IN_PROGRESS: read the running slot now (the cached one may be
// a poll old) and follow it instead of failing. A slot that already finished
// is still followed: its terminal state is the edge the hook acts on. When
// the read fails, follow this repo (never the cached slot's, maybe an old one).
async function attachToRunning(ctx, repo) {
  let slot;
  try {
    slot = await ctx.queryClient.fetchQuery({ queryKey: projectsKeys.clone(), queryFn: ctx.api.getCloneStatus, staleTime: 0 });
  } catch (err) {
    console.warn('[analyzeLaunchStart] clone status read after a 409 failed:', err);
    ctx.set.setPending({ repo, requested: repo, stale: ctx.slot()?.finishedAt ?? null, conflict: true });
    return;
  }
  ctx.set.setPending({
    repo: slot?.repo || repo,
    requested: repo,
    stale: isCloneActive(slot) ? (slot.finishedAt ?? null) : null,
    conflict: true,
  });
}

async function postClone(ctx, { repo, cloneDest, standardIds }) {
  // The slot as it stood before this post: a terminal state with its
  // finishedAt is an earlier job's, never this one's.
  const stale = ctx.slot()?.finishedAt ?? null;
  const res = await ctx.api.registerProject({ repo, ...(cloneDest ? { cloneDest } : {}) });
  if (res?.started) {
    ctx.set.setPending({ repo: res.repo || repo, requested: repo, stale, conflict: false });
    // Wakes the app-level poller (slow while idle) so progress shows at once.
    ctx.queryClient.invalidateQueries({ queryKey: projectsKeys.clone() })
      .catch((err) => console.warn('[analyzeLaunchStart] clone status refetch failed:', err));
    return;
  }
  ctx.wizard.succeedScan(res.projectId, res.scanData);
  ctx.launch({ projectId: res.projectId, repo, standardIds });
}

/**
 * A git url: probe access first (an unreachable verdict opens the access
 * panel and posts nothing), then post the clone, which the server runs as a
 * job (202). The hook follows the slot from there.
 */
export async function startUrl(ctx, request) {
  const { repo } = request;
  try {
    const access = await ctx.api.probeGit(repo);
    if (!access.reachable) {
      ctx.set.setAccessFailure({ kind: access.kind, detail: access.detail || '', host: access.host || '', isGitHub: Boolean(access.isGitHub) });
      return;
    }
    await postClone(ctx, request);
  } catch (err) {
    if (err?.code === CODE_CLONE_IN_PROGRESS) { await attachToRunning(ctx, repo); return; }
    if (await resumed(ctx, err, request)) return;
    const access = accessFailureFrom(err);
    if (access) { ctx.set.setAccessFailure(access); return; }
    ctx.set.setStartError({ message: apiErrorMessage(err, 'onboarding.cloneFailed'), detail: apiErrorDetail(err) });
  }
}
