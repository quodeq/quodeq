import { projectsKeys } from '../../../api/queryKeys.js';
import { apiErrorMessage, apiErrorDetail } from '../../../strings/apiErrors.js';
import { t } from '../../../strings/index.js';
import { accessFailureFrom } from '../../github-access/accessFailure.js';
import { resumedExisting } from './resumeExisting.js';

// POST /api/projects refuses a second clone while one runs (the slot is shared).
const CODE_CLONE_IN_PROGRESS = 'CLONE_IN_PROGRESS';

/**
 * How `add` starts, as plain async steps over a context the hook builds
 * each call:
 *   ctx.api          registerProject, probeGit
 *   ctx.queryClient  the clone slot's cache (projectsKeys.clone())
 *   ctx.wizard       startScan, succeedScan, failScan
 *   ctx.set          setAccessFailure, setStartError
 *   ctx.tryResume    makeTryResumeExisting's resume of a registered repo
 *   ctx.added        ({ projectId, cloning }) => void; the panel closes on it.
 *                    projectId is the registered project (null while a clone
 *                    job runs), cloning says the Repositories tile carries on.
 *                    A no-op once the panel closed (it may run after a slow await).
 */

// A repo the server already holds (409 + existingProjectId) is resumed and
// handed over as added, not failed; true when it was.
async function resumed(ctx, err) {
  if (!(await resumedExisting(err, ctx.tryResume))) return false;
  ctx.added({ projectId: err.existingProjectId, cloning: false });
  return true;
}

/**
 * A local folder registers synchronously (200 with the project and its scan)
 * and the panel hands the project over at once; the clone slot is never involved.
 */
export async function startFolder(ctx, { repo }) {
  ctx.wizard.startScan();
  try {
    const { projectId, scanData } = await ctx.api.registerProject({ repo });
    ctx.wizard.succeedScan(projectId, scanData);
    ctx.added({ projectId, cloning: false });
  } catch (err) {
    if (await resumed(ctx, err)) return;
    const message = apiErrorMessage(err, 'onboarding.scanFailed');
    ctx.wizard.failScan({ message, status: err.status, code: err.code });
    ctx.set.setStartError({ message, detail: apiErrorDetail(err) });
  }
}

async function postClone(ctx, { repo, cloneDest }) {
  const res = await ctx.api.registerProject({ repo, ...(cloneDest ? { cloneDest } : {}) });
  if (res?.started) {
    // Wakes the app-level poller (slow while idle) so the tile shows at once.
    ctx.queryClient.invalidateQueries({ queryKey: projectsKeys.clone() })
      .catch((err) => console.warn('[analyzeLaunchStart] clone status refetch failed:', err));
    ctx.added({ projectId: null, cloning: true });
    return;
  }
  ctx.wizard.succeedScan(res.projectId, res.scanData);
  ctx.added({ projectId: res.projectId, cloning: false });
}

/**
 * A git url: probe access first (an unreachable verdict opens the access
 * panel and posts nothing), then post the clone, which the server runs as a
 * job (202). The Repositories tab's tile follows it from there. A second
 * clone while one runs is refused: the panel says so and keeps the url.
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
    if (err?.code === CODE_CLONE_IN_PROGRESS) {
      ctx.set.setStartError({ message: t('onboarding.cloneRunningElsewhere'), detail: '' });
      return;
    }
    if (await resumed(ctx, err)) return;
    const access = accessFailureFrom(err);
    if (access) { ctx.set.setAccessFailure(access); return; }
    ctx.set.setStartError({ message: apiErrorMessage(err, 'onboarding.cloneFailed'), detail: apiErrorDetail(err) });
  }
}
