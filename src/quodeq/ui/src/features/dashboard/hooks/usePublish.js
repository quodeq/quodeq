import { useCallback, useEffect, useRef, useState } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';

const POLL_INTERVAL_MS = 2000;

function buildPublishedAtMap(list) {
  const map = {};
  for (const p of list || []) {
    const id = p.id || p.name;
    if (id && p.publishedAt) map[id] = p.publishedAt;
  }
  return map;
}

/**
 * usePublish -- the LOCAL Projects tab's publish action + job progress.
 *
 * Local project cards need two things the plain /api/projects listing never
 * carries: whether a shared repo is configured at all (to decide whether the
 * publish button shows), and each project's publishedAt, which only exists
 * on the SHARED project list (git log of the clone -- see
 * services/shared_repo.py's published_meta()). This hook fetches both with
 * `refresh: false` -- it must never force an actual git fetch of the remote
 * just because the user is looking at their LOCAL projects; that stays
 * exclusively the online sub-tab's job (see useSharedProjects.js's
 * refresh-on-entry contract). `enabled` lets the caller skip this fetch
 * entirely when there is nothing to decorate (e.g. the online sub-tab is
 * active, or there are no local projects yet).
 *
 * The publish trigger and its job-progress polling live here rather than in
 * a component per the Task 20 design: a single publish job is global to the
 * whole app (one project publishing at a time, enforced server-side), so
 * "is anything publishing right now" has to be state shared by every local
 * card's button, not something any one card owns.
 */
export function usePublish({ enabled = true } = {}) {
  const { getSharedStatus, sharedListProjects, publishProject } = useApi();

  const [configured, setConfigured] = useState(false);
  const [publishedAtByProject, setPublishedAtByProject] = useState({});
  // idle | running | done | error -- mirrors the backend's global publish job.
  const [publishState, setPublishState] = useState('idle');
  const [publishingProject, setPublishingProject] = useState(null);
  const [publishError, setPublishError] = useState(null);
  const [publishErrorProject, setPublishErrorProject] = useState(null);

  // In-flight guard for the publish trigger -- same synchronous-ref idiom as
  // useSharedProjects' connectingRef/refreshingRef/pullingRef. A ref (not
  // state) because it must be readable synchronously on the very next call,
  // before any state update triggered by this call has committed/re-rendered.
  // It only guards the POST round-trip itself (a rapid double-click/Enter
  // race), not the whole background job -- once the POST resolves, a click
  // on a DIFFERENT card's button is expected to reach the backend and get a
  // real 409, which is how that card's own inline error gets populated.
  const publishingRef = useRef(false);
  const pollTimerRef = useRef(null);
  const mountedRef = useRef(true);
  // Mirrors `publishingProject` state synchronously, so the poll callback
  // (memoized once, reused across ticks) always reads the latest value
  // instead of whatever was captured in its closure at creation time.
  const publishingProjectRef = useRef(null);

  const setPublishingProjectBoth = useCallback((id) => {
    publishingProjectRef.current = id;
    setPublishingProject(id);
  }, []);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const fetchSharedList = useCallback(async () => {
    try {
      const envelope = await sharedListProjects({ refresh: false });
      if (!mountedRef.current) return;
      setPublishedAtByProject(buildPublishedAtMap(envelope?.projects));
    } catch {
      // Best effort -- a failed refresh just leaves the "published <time
      // ago>" meta stale on cards; it is not primary content worth an
      // error banner over.
    }
  }, [sharedListProjects]);

  const checkStatus = useCallback(async () => {
    let data;
    try {
      data = await getSharedStatus();
    } catch {
      return; // transient poll failure -- the job keeps running server-side regardless; try again next tick
    }
    if (!mountedRef.current) return;
    const publish = data?.publish || {};
    if (publish.state === 'running') return; // keep polling
    stopPolling();
    const finishedProject = publish.project ?? publishingProjectRef.current;
    if (publish.state === 'error') {
      setPublishState('error');
      setPublishError(publish.error || 'publish failed');
      setPublishErrorProject(finishedProject);
    } else {
      // 'done' (or an unexpected 'idle') -- refresh the shared list once so
      // the card that just finished gets its "published <relative time>"
      // meta line updated. Also clear any error left over from a PREVIOUS
      // failed attempt on this same project (single global job -- only one
      // publish is ever in flight): without this, a retry that succeeds
      // still shows the stale error banner under the card, since CardFooter
      // keys showError on publishErrorProject alone, not on publishState.
      setPublishState('done');
      setPublishError(null);
      setPublishErrorProject(null);
      await fetchSharedList();
    }
    setPublishingProjectBoth(null);
  }, [getSharedStatus, stopPolling, fetchSharedList, setPublishingProjectBoth]);

  const loadStatus = useCallback(async () => {
    try {
      const data = await getSharedStatus();
      if (!mountedRef.current) return;
      setConfigured(!!data?.configured);
      if (data?.configured) {
        await fetchSharedList();
      }
      const publish = data?.publish || {};
      if (publish.state === 'running') {
        // A job was already in flight before this mount (e.g. the user
        // navigated away mid-publish and back) -- pick polling back up
        // rather than showing every button as idle while it's really not.
        setPublishState('running');
        setPublishingProjectBoth(publish.project ?? null);
        stopPolling();
        pollTimerRef.current = setInterval(checkStatus, POLL_INTERVAL_MS);
      } else if (publishingProjectRef.current) {
        // The hook was disabled and re-enabled (tab toggle) while a job was
        // running. The fetched status is no longer running, meaning the job
        // completed while away -- reconcile local state to match the server.
        if (publish.state === 'error') {
          setPublishState('error');
          setPublishError(publish.error || 'publish failed');
          setPublishErrorProject(publish.project ?? publishingProjectRef.current);
        } else {
          // 'done' or an unexpected 'idle' -- refresh the shared list once
          setPublishState('done');
          await fetchSharedList();
        }
        setPublishingProjectBoth(null);
      }
    } catch {
      // Best effort -- this is a supporting meta fetch (button visibility +
      // published-at decoration), not primary page content.
    }
  }, [getSharedStatus, fetchSharedList, checkStatus, stopPolling, setPublishingProjectBoth]);

  useEffect(() => {
    mountedRef.current = true;
    if (enabled) loadStatus();
    return () => {
      mountedRef.current = false;
      stopPolling();
    };
    // Runs once per mount (or when `enabled` flips true) -- see the
    // refresh-on-entry-style note above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);

  const publish = useCallback(async (projectId) => {
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
      stopPolling();
      pollTimerRef.current = setInterval(checkStatus, POLL_INTERVAL_MS);
    } catch (err) {
      setPublishError(err?.message || 'failed to start publish');
      setPublishErrorProject(projectId);
    } finally {
      publishingRef.current = false;
    }
  }, [publishProject, checkStatus, stopPolling, setPublishingProjectBoth]);

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
