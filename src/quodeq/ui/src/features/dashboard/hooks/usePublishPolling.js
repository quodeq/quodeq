import { useCallback, useRef, useState } from 'react';
import { sharedKeys } from '../../../api/queryKeys.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';

const POLL_INTERVAL_MS = 2000;

// idle | running | done | error state, the polling refs, and the poll-tick
// machinery for usePublish's global publish job. Extracted verbatim from
// usePublish.js -- publishingRef and mountedRef stay owned by usePublish.js
// itself (they also guard the publish() trigger and the hook's own mount
// lifecycle, which are outside this extraction; mountedRef is passed in so
// checkStatus can still read it), but publishingProjectRef, pollTimerRef,
// stopPolling/startPolling, refreshListAfterCompletion, and checkStatus move
// here as one unit since they only ever operate on each other.
// Imperative and cache-key-targeted rather than a plain refetch of usePublish's
// own (possibly disabled) listQuery -- fetchQuery ignores `enabled` entirely,
// so the meta line updates even when the hook was mounted with
// `enabled: false` (e.g. no local projects at the moment the job that just
// finished was started for a project elsewhere).
function useRefreshListAfterCompletion(queryClient, sharedListProjects) {
  return useCallback(() => {
    return queryClient
      .fetchQuery({
        queryKey: sharedKeys.list(),
        queryFn: () => sharedListProjects({ refresh: false }),
        // Force the fetch: the production QueryClient's default staleTime is
        // 30s (see api/queryClient.js), so without this a still-fresh cache
        // entry would let fetchQuery resolve without ever hitting the
        // network -- silently contradicting the comment above this function.
        staleTime: 0,
      })
      .catch(() => {
        // Best effort -- a failed refresh just leaves the "published <time
        // ago>" meta stale on cards; it is not primary content worth an
        // error banner over.
      });
  }, [queryClient, sharedListProjects]);
}

function useCheckStatus({ getSharedStatus, mountedRef, stopPolling, applyOptimisticPublish, refreshListAfterCompletion, publishingProjectRef, setPublishState, setPublishError, setPublishErrorProject, setPublishingProjectBoth }) {
  return useCallback(async () => {
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
      // No `code` on the polled payload yet -- services/shared_publish.py's
      // PublishStatus only ever sets {state, project, runs, error,
      // finished_at}, so apiErrorMessage falls back to the raw message here
      // exactly like the old `publish.error || t(...)` did. Routing it
      // through the shared mapper anyway keeps this call site consistent
      // with the rest of the app and makes it forward-compatible the moment
      // the backend starts emitting a discriminating code.
      setPublishError(apiErrorMessage({ message: publish.error }, 'projects.publishFailed'));
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
      // Flip the card BEFORE the network round trip below, then let the
      // authoritative refresh overwrite this optimistic entry once it lands.
      if (finishedProject) applyOptimisticPublish(finishedProject);
      await refreshListAfterCompletion();
    }
    setPublishingProjectBoth(null);
  }, [getSharedStatus, stopPolling, applyOptimisticPublish, refreshListAfterCompletion, setPublishingProjectBoth]);
}

// idle | running | done | error -- mirrors the backend's global publish job.
// publishingProjectRef mirrors `publishingProject` state synchronously, so
// the poll callback (memoized once, reused across ticks) always reads the
// latest value instead of whatever was captured in its closure at creation
// time.
function usePublishJobState() {
  const [publishState, setPublishState] = useState('idle');
  const [publishingProject, setPublishingProject] = useState(null);
  const [publishError, setPublishError] = useState(null);
  const [publishErrorProject, setPublishErrorProject] = useState(null);
  const publishingProjectRef = useRef(null);

  const setPublishingProjectBoth = useCallback((id) => {
    publishingProjectRef.current = id;
    setPublishingProject(id);
  }, []);

  return {
    publishState, publishingProject, publishError, publishErrorProject,
    setPublishState, setPublishError, setPublishErrorProject,
    publishingProjectRef, setPublishingProjectBoth,
  };
}

export function usePublishPolling({ queryClient, sharedListProjects, getSharedStatus, applyOptimisticPublish, mountedRef }) {
  const {
    publishState, publishingProject, publishError, publishErrorProject,
    setPublishState, setPublishError, setPublishErrorProject,
    publishingProjectRef, setPublishingProjectBoth,
  } = usePublishJobState();

  const pollTimerRef = useRef(null);
  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const refreshListAfterCompletion = useRefreshListAfterCompletion(queryClient, sharedListProjects);
  const checkStatus = useCheckStatus({
    getSharedStatus, mountedRef, stopPolling, applyOptimisticPublish, refreshListAfterCompletion,
    publishingProjectRef, setPublishState, setPublishError, setPublishErrorProject, setPublishingProjectBoth,
  });

  const startPolling = useCallback(() => {
    stopPolling();
    pollTimerRef.current = setInterval(checkStatus, POLL_INTERVAL_MS);
  }, [stopPolling, checkStatus]);

  return {
    publishState,
    publishingProject,
    publishError,
    publishErrorProject,
    setPublishState,
    setPublishError,
    setPublishErrorProject,
    publishingProjectRef,
    setPublishingProjectBoth,
    stopPolling,
    startPolling,
    checkStatus,
    refreshListAfterCompletion,
  };
}
