import { useCallback, useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { apiErrorMessage } from '../../../strings/apiErrors.js';
import { usePublishQueries } from './usePublishQueries.js';
import { usePublishPolling } from './usePublishPolling.js';
import { useApplyOptimisticPublish } from './publishOptimisticCache.js';

/**
 * usePublish -- publish action + job progress for local cards on the merged
 * Projects page (one list, no tabs -- see ProjectsPage.jsx).
 *
 * Local project cards need two things the plain /api/projects listing never
 * carries: whether a shared repo is configured at all (to decide whether the
 * publish button shows), and each project's publishedAt, which only exists
 * on the SHARED project list (git log of the clone -- see
 * services/shared_repo.py's published_meta()). `configured` and
 * `publishedAtByProject` derive from the SAME two react-query queries
 * useSharedProjects itself reads -- `sharedKeys.status()` and
 * `sharedKeys.list()` -- so mounting both hooks together never issues
 * duplicate requests: react-query dedupes any active observers sharing a
 * key (audit C6). Both queries fetch with `refresh: false` -- this hook
 * must never force an actual git fetch of the remote just because a local
 * card is rendering; that stays exclusively useSharedProjects' background-
 * refresh job (see that hook's own doc comment). `enabled` lets the caller
 * skip these queries entirely when there is nothing to decorate (e.g. there
 * are no local projects yet) -- though if some OTHER mounted consumer
 * (typically useSharedProjects itself) already has the same query active,
 * the shared cache entry is fetched regardless; `enabled` here only governs
 * whether THIS hook's own observer, in isolation, would trigger it.
 *
 * The publish trigger and its job-progress polling live here rather than in
 * a component per the Task 20 design: a single publish job is global to the
 * whole app (one project publishing at a time, enforced server-side), so
 * "is anything publishing right now" has to be state shared by every local
 * card's button, not something any one card owns. Polling during a RUNNING
 * publish calls `getSharedStatus()` directly every 2s -- deliberately
 * bypassing the query cache -- because it's polling job status, not list
 * data; routing it through `sharedKeys.status()` would churn that cache
 * (and every other consumer re-rendering off it) every 2s for no reason.
 * Once the job finishes, the shared LIST query IS the right thing to
 * refresh (so publishedAtByProject picks up the new publishedAt) -- that
 * goes through `queryClient.fetchQuery`, which (unlike `enabled`) ignores
 * this hook's own gating and always performs the fetch, updating the same
 * cache entry every other consumer reads.
 */
function usePublishTrigger({ publishProject, startPolling, publishingRef, publishingLocalRef, setPublishState, setPublishError, setPublishErrorProject, setPublishingProjectBoth }) {
  return useCallback(async (projectId, localProject) => {
    if (publishingRef.current) return; // already in flight -- ignore the repeat click
    publishingRef.current = true;
    setPublishError(null);
    setPublishErrorProject(null);
    try {
      await publishProject(projectId);
      // Only now do we know this click genuinely started the job -- a
      // rejected POST (see catch below) must never stomp on a different
      // project's already-running job, so publishState/publishingProject
      // are set exclusively on confirmed outcomes (this success, or a poll
      // result), never optimistically before the POST resolves.
      setPublishState('running');
      setPublishingProjectBoth(projectId);
      // Stashed for the done-branch's optimistic cache patch (see
      // applyOptimisticPublish) -- the caller's local project object is the
      // only place originUrl/latestRunId/latestDoneRunId are known from,
      // since the backend's publish/status payloads never echo them back.
      publishingLocalRef.current = localProject ?? null;
      startPolling();
    } catch (err) {
      setPublishError(apiErrorMessage(err, 'projects.publishStartFailed'));
      setPublishErrorProject(projectId);
    } finally {
      publishingRef.current = false;
    }
  }, [publishProject, startPolling, setPublishState, setPublishError, setPublishErrorProject, setPublishingProjectBoth]);
}

// Mount/unmount lifecycle -- guards the async checkStatus/refreshList
// continuations against setting state after unmount, and always clears any
// live interval on the way out. Polling must also stop whenever `enabled`
// toggles (either direction) -- a tab switch away must not keep ticking in
// the background for a hook the caller has disabled.
function usePublishLifecycleEffects({ mountedRef, stopPolling, enabled }) {
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      stopPolling();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount/unmount only
  }, []);

  useEffect(() => {
    return () => { stopPolling(); };
  }, [enabled, stopPolling]);
}

// Reconcile local publish state whenever a fresh status lands (mount,
// re-enable after being disabled while a job was running, or any OTHER
// consumer's invalidation of sharedKeys.status() -- e.g. useSharedProjects'
// own refresh()). Mirrors the old loadStatus()'s two branches exactly: the
// server saying "running" is adopted unconditionally (a job started
// elsewhere -- a CLI publish, or before this mount -- surfaces here too);
// otherwise, if THIS hook was locally tracking a running job that the fresh
// status no longer reports as running, the job finished while this hook
// wasn't polling (disabled, or a fresh mount after external completion) and
// local state is reconciled to match the server.
function useReconcilePublishStatus({ statusQueryData, setPublishState, setPublishError, setPublishErrorProject, setPublishingProjectBoth, publishingProjectRef, startPolling, stopPolling, applyOptimisticPublish, refreshListAfterCompletion }) {
  useEffect(() => {
    const publish = statusQueryData?.publish;
    if (!publish) return;
    if (publish.state === 'running') {
      setPublishState('running');
      setPublishingProjectBoth(publish.project ?? null);
      startPolling();
    } else if (publishingProjectRef.current) {
      stopPolling();
      if (publish.state === 'error') {
        setPublishState('error');
        // No `code` on this payload either -- see usePublishPolling.js's
        // checkStatus for the full explanation (services/shared_publish.py's
        // PublishStatus never sets one). Routed through apiErrorMessage for
        // the same reason: consistency with the rest of the app, and
        // forward-compatible the moment the backend starts emitting one.
        setPublishError(apiErrorMessage({ message: publish.error }, 'projects.publishFailed'));
        setPublishErrorProject(publish.project ?? publishingProjectRef.current);
      } else {
        setPublishState('done');
        setPublishError(null);
        setPublishErrorProject(null);
        const doneProject = publish.project ?? publishingProjectRef.current;
        if (doneProject) applyOptimisticPublish(doneProject);
        refreshListAfterCompletion();
      }
      setPublishingProjectBoth(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-run on a genuinely new status payload
  }, [statusQueryData]);
}

// publishingRef: in-flight guard for the publish trigger -- same
// synchronous-ref idiom as useSharedProjects' connectingRef/pullingRef. A ref
// (not state) because it must be readable synchronously on the very next
// call, before any state update triggered by this call has committed/
// re-rendered. It only guards the POST round-trip itself (a rapid
// double-click/Enter race), not the whole background job -- once the POST
// resolves, a click on a DIFFERENT card's button is expected to reach the
// backend and get a real 409, which is how that card's own inline error gets
// populated.
// publishingLocalRef: the local project object passed to the most recent
// publish() call -- carries the identity fields (name, originUrl,
// latestRunId, latestDoneRunId) the optimistic cache patch needs but the
// backend's status/publish payload doesn't echo back.
function usePublishRefGuards() {
  const publishingRef = useRef(false);
  const mountedRef = useRef(true);
  const publishingLocalRef = useRef(null);
  return { publishingRef, mountedRef, publishingLocalRef };
}

export function usePublish({ enabled = true } = {}) {
  const { getSharedStatus, sharedListProjects, publishProject } = useApi();
  const queryClient = useQueryClient();

  const { statusQuery, configured, publishedAtByProject } = usePublishQueries({ enabled, getSharedStatus, sharedListProjects });
  const { publishingRef, mountedRef, publishingLocalRef } = usePublishRefGuards();

  const applyOptimisticPublish = useApplyOptimisticPublish({ queryClient, publishingLocalRef });

  const {
    publishState, publishingProject, publishError, publishErrorProject,
    setPublishState, setPublishError, setPublishErrorProject,
    publishingProjectRef, setPublishingProjectBoth,
    stopPolling, startPolling, refreshListAfterCompletion,
  } = usePublishPolling({ queryClient, sharedListProjects, getSharedStatus, applyOptimisticPublish, mountedRef });

  const publish = usePublishTrigger({
    publishProject, startPolling, publishingRef, publishingLocalRef,
    setPublishState, setPublishError, setPublishErrorProject, setPublishingProjectBoth,
  });

  usePublishLifecycleEffects({ mountedRef, stopPolling, enabled });

  useReconcilePublishStatus({
    statusQueryData: statusQuery.data,
    setPublishState, setPublishError, setPublishErrorProject, setPublishingProjectBoth,
    publishingProjectRef, startPolling, stopPolling, applyOptimisticPublish, refreshListAfterCompletion,
  });

  return {
    configured,
    publishedAtByProject,
    publishState,
    publishingProject,
    publishError,
    publishErrorProject,
    publish,
  };
}
