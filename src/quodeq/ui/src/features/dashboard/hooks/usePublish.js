import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { sharedKeys } from '../../../api/queryKeys.js';

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
export function usePublish({ enabled = true } = {}) {
  const { getSharedStatus, sharedListProjects, publishProject } = useApi();
  const queryClient = useQueryClient();

  const statusQuery = useQuery({
    queryKey: sharedKeys.status(),
    queryFn: getSharedStatus,
    enabled,
  });

  const configured = !!statusQuery.data?.configured;

  const listQuery = useQuery({
    queryKey: sharedKeys.list(),
    queryFn: () => sharedListProjects({ refresh: false }),
    enabled: enabled && configured,
  });

  const publishedAtByProject = useMemo(
    () => buildPublishedAtMap(listQuery.data?.projects),
    [listQuery.data],
  );

  // idle | running | done | error -- mirrors the backend's global publish job.
  const [publishState, setPublishState] = useState('idle');
  const [publishingProject, setPublishingProject] = useState(null);
  const [publishError, setPublishError] = useState(null);
  const [publishErrorProject, setPublishErrorProject] = useState(null);

  // In-flight guard for the publish trigger -- same synchronous-ref idiom as
  // useSharedProjects' connectingRef/pullingRef. A ref (not state) because
  // it must be readable synchronously on the very next call, before any
  // state update triggered by this call has committed/re-rendered. It only
  // guards the POST round-trip itself (a rapid double-click/Enter race),
  // not the whole background job -- once the POST resolves, a click on a
  // DIFFERENT card's button is expected to reach the backend and get a real
  // 409, which is how that card's own inline error gets populated.
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

  const refreshListAfterCompletion = useCallback(() => {
    // Imperative and cache-key-targeted rather than a plain refetch of
    // THIS hook's own (possibly disabled) listQuery -- fetchQuery ignores
    // `enabled` entirely, so the meta line updates even when this hook was
    // mounted with `enabled: false` (e.g. no local projects at the moment
    // the job that just finished was started for a project elsewhere).
    return queryClient
      .fetchQuery({ queryKey: sharedKeys.list(), queryFn: () => sharedListProjects({ refresh: false }) })
      .catch(() => {
        // Best effort -- a failed refresh just leaves the "published <time
        // ago>" meta stale on cards; it is not primary content worth an
        // error banner over.
      });
  }, [queryClient, sharedListProjects]);

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
      await refreshListAfterCompletion();
    }
    setPublishingProjectBoth(null);
  }, [getSharedStatus, stopPolling, refreshListAfterCompletion, setPublishingProjectBoth]);

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

  // Mount/unmount lifecycle -- guards the async checkStatus/refreshList
  // continuations above against setting state after unmount, and always
  // clears any live interval on the way out.
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      stopPolling();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount/unmount only
  }, []);

  // Polling must stop whenever `enabled` toggles (either direction), same
  // as the old effect's cleanup used to -- a tab switch away must not keep
  // ticking in the background for a hook the caller has disabled.
  useEffect(() => {
    return () => { stopPolling(); };
  }, [enabled, stopPolling]);

  // Reconcile local publish state whenever a fresh status lands (mount,
  // re-enable after being disabled while a job was running, or any OTHER
  // consumer's invalidation of sharedKeys.status() -- e.g. useSharedProjects'
  // own refresh()). Mirrors the old loadStatus()'s two branches exactly:
  // the server saying "running" is adopted unconditionally (a job started
  // elsewhere -- a CLI publish, or before this mount -- surfaces here too);
  // otherwise, if THIS hook was locally tracking a running job that the
  // fresh status no longer reports as running, the job finished while this
  // hook wasn't polling (disabled, or a fresh mount after external
  // completion) and local state is reconciled to match the server.
  useEffect(() => {
    const publish = statusQuery.data?.publish;
    if (!publish) return;
    if (publish.state === 'running') {
      setPublishState('running');
      setPublishingProjectBoth(publish.project ?? null);
      stopPolling();
      pollTimerRef.current = setInterval(checkStatus, POLL_INTERVAL_MS);
    } else if (publishingProjectRef.current) {
      stopPolling();
      if (publish.state === 'error') {
        setPublishState('error');
        setPublishError(publish.error || 'publish failed');
        setPublishErrorProject(publish.project ?? publishingProjectRef.current);
      } else {
        setPublishState('done');
        setPublishError(null);
        setPublishErrorProject(null);
        refreshListAfterCompletion();
      }
      setPublishingProjectBoth(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-run on a genuinely new status payload
  }, [statusQuery.data]);

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
