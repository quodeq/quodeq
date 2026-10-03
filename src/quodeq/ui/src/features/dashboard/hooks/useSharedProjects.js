/**
 * Shared-repo status and project list for the merged Projects page (one list,
 * no tabs -- see ProjectsPage.jsx). Feeds the shared-only cards, the sync
 * strip (SyncStrip), and -- through useMergedProjects -- every local card's
 * chips and action.
 *
 * Status comes from useSyncStatus, the app's only poller of
 * GET /api/shared/status: it carries whether sharing is configured, when it
 * last synced, and the connect, refresh and pull jobs the server runs in the
 * background. The list is a react-query query on `sharedKeys.list()` that
 * always passes `refresh: false`, so the UI renders instantly from whatever
 * the server has cached and never blocks on a git fetch. useSyncStatus
 * invalidates that list when a job finishes (the job has already warmed the
 * server's listing by then), so this hook only re-lists on its own to heal an
 * errored list on retry, and nothing refreshes the remote on mount:
 * `refresh()` is the strip's explicit "update" action and starts the job.
 *
 * Error handling has two tiers. A failed *initial* load (status, or the first
 * list once configured, i.e. before either has ever produced data) surfaces
 * `error`, since there is nothing to show yet. A failed *refresh* of an
 * already-loaded page does NOT blank the view: it flags `stale` (the refresh
 * job ended in ERROR, or could not be started) so the sync strip can show
 * "update failed, showing results from <when>" over the still-valid
 * last-known listing.
 *
 * `lastSynced` seeds from the STATUS payload, so a list-only failure still
 * shows when the repo last synced instead of "not synced yet"; once the list
 * has its own envelope, that value overrides it.
 *
 * `refresh()` also re-reads the status, so it doubles as the retry
 * affordance behind the strip's "retry" even when the
 * original failure was the status fetch itself.
 */
import { useCallback, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { isSlotActive } from '../../../api/syncStatus.js';
import { useSyncStatus } from '../../../hooks/useSyncStatus.js';
import { SYNC_PHASE } from '../../../vocab/syncPhase.js';
import { t } from '../../../strings/index.js';
import { connectSlotError } from '../../../hooks/connectSlotError.js';
import { sharedListQueryOptions } from './sharedQueryOptions.js';
import { useSharedActions } from './useSharedActions.js';
import { useSharedStatusAndList } from './useSharedStatusAndList.js';

/**
 * Message for an INITIAL load failure, meaning no data has ever landed for
 * that query. A background refresh failure after data already exists is
 * `stale`, not `error`, so it never blanks an already-working view.
 */
function deriveSharedError({ sync, listQuery, configured }) {
  if (sync.isError && sync.status === undefined) {
    return sync.error?.message || t('projects.sharedStatusFailed');
  }
  if (configured && listQuery.isError && listQuery.data === undefined) {
    return listQuery.error?.message || t('projects.sharedStatusFailed');
  }
  return null;
}

/**
 * Freshness flags. `loading` holds until BOTH the status query and (when
 * configured) the list query have settled at least once. isLoading, not
 * isPending, is "no data yet AND actively fetching", so an unconfigured
 * repo's never-run list query does not hold it true forever.
 */
function deriveSharedFreshness({ sync, listQuery, configured, startFailed }) {
  return {
    stale: startFailed || sync.refresh?.phase === SYNC_PHASE.ERROR || !!listQuery.data?.stale,
    loading: sync.isLoading || (configured && listQuery.isLoading),
  };
}

function deriveSharedProjectsState({ sync, listQuery, configured, startFailed }) {
  // Gated on `configured`, not just read off listQuery.data: the list query
  // is disabled (not removed) when unconfigured, so a lingering cache entry
  // from before a disconnect (or from a DIFFERENT shared repo before a
  // reconnect) would otherwise keep rendering shared cards -- with live pull
  // buttons -- on a page that has nothing connected (ghost shared cards
  // after disconnect).
  const projects = configured ? (listQuery.data?.projects || []) : [];
  return {
    url: sync.url,
    projects,
    lastSynced: listQuery.data?.lastSynced ?? sync.lastSynced,
    ...deriveSharedFreshness({ sync, listQuery, configured, startFailed }),
    error: deriveSharedError({ sync, listQuery, configured }),
  };
}

// Starts a refresh job and re-reads the status so the strip flips to
// "refreshing" now rather than at the next idle poll. A failure to start
// keeps the page's data and flags it stale; the exact API message isn't
// shown, the stale banner copy is fixed regardless of cause. A list that
// errored (it timed out on a cold clone) is re-read too, so "retry" heals the
// list even when no refresh job reaches DONE to invalidate it.
function useRefreshStart({ startRefresh, refetchStatus, listQuery }) {
  const [startFailed, setStartFailed] = useState(false);
  const { isError: listFailed, refetch: refetchList } = listQuery;
  const refresh = useCallback(async () => {
    setStartFailed(false);
    try {
      await startRefresh();
    } catch (err) {
      console.warn('[useSharedProjects] refresh failed to start:', err);
      setStartFailed(true);
    }
    await refetchStatus();
    if (listFailed) await refetchList();
  }, [startRefresh, refetchStatus, listFailed, refetchList]);
  return { startFailed, refresh };
}

/**
 * The shared-repo screen's data and actions: whether sharing is configured,
 * the remote project list and its freshness, plus connect, refresh and pull.
 * All three actions only start a background job; progress and outcome come
 * back through the sync status (`pullSlot` is the pull job's, for
 * usePullToLocal).
 */
export function useSharedProjects() {
  const { sharedListProjects, connectShared, startRefresh, startPull } = useApi();

  const sync = useSyncStatus();
  const { configured } = sync;
  const listQuery = useQuery(sharedListQueryOptions({ sharedListProjects, configured, status: sync.status }));

  const actions = useSharedActions({ connectShared, startPull });
  const pull = useCallback(async (projectId, action) => {
    const started = await actions.pull(projectId, action);
    await sync.refetch(); // show the running job now, not at the next idle poll
    return started;
  }, [actions.pull, sync.refetch]);
  // The last URL this screen tried, so a failed connect can be retried from the strip.
  const [lastConnectUrl, setLastConnectUrl] = useState(null);
  const connect = useCallback(async (nextUrl) => {
    setLastConnectUrl(nextUrl);
    await actions.connect(nextUrl);
    await sync.refetch(); // show the running job now, not at the next idle poll
  }, [actions.connect, sync.refetch]);
  const { startFailed, refresh } = useRefreshStart({ startRefresh, refetchStatus: sync.refetch, listQuery });

  const { url, projects, lastSynced, stale, loading, error } = deriveSharedProjectsState({
    sync, listQuery, configured, startFailed,
  });

  return {
    configured, url, projects, lastSynced, stale,
    loading, error,
    // The raw status for the sync strip; `offline` is a failed poll over a
    // status that last said a repository is configured (the strip keeps
    // showing the last-known results).
    status: sync.status,
    offline: sync.isError && sync.status !== undefined && configured,
    // An update that failed outside the refresh slot: the job could not be
    // started, or the server marked the cached listing stale.
    updateFailed: startFailed || Boolean(listQuery.data?.stale),
    connecting: actions.connecting || isSlotActive(sync.connect),
    connectError: actions.connectError ?? connectSlotError(sync.connect, 'projects.connectFailed'),
    // The PUT's own rejection, apart from the slot's: closing a failed connect hides only the latter.
    connectStartError: actions.connectError ?? null,
    accessFailure: actions.accessFailure,
    connect, lastConnectUrl,
    refreshing: isSlotActive(sync.refresh), refresh,
    pull, pullSlot: sync.pull,
  };
}

// This signal feeds the derived wizard auto-open and no-projects landing
// redirect, both re-evaluated whenever it changes. Focus revalidation belongs to the pages that render the list, not
// here -- refetching on focus would let hasContent flip mid-session for users
// who never open those pages. This is a per-observer option and does not
// affect useSharedProjects' own observers on the same query keys.
const SIGNAL_OBSERVER_OPTIONS = { refetchOnWindowFocus: false };

/**
 * useSharedContentSignal — passive "does the shared repo have anything to
 * show?" signal for App-level flow decisions (wizard auto-open, initial
 * landing, zero-local empty states). Reads the SAME sharedKeys.status()/
 * sharedKeys.list() cache entries as useSharedProjects (react-query dedupes
 * by key, so mounting both costs one fetch each), but deliberately has no
 * polling, no mutations, and no error surface: a failed status
 * or list load settles as hasContent=false, which falls back to today's
 * local-only flow.
 *
 * settled: the decision inputs are final for this load — status resolved or
 * errored, and (when configured) the first list fetch resolved or errored.
 * Consumers defer their decision (without latching) until settled so the
 * wizard doesn't flash open over a remote list that was about to appear.
 */
export function useSharedContentSignal() {
  const { getSharedStatus, sharedListProjects } = useApi();

  const { statusQuery, configured, listQuery } = useSharedStatusAndList({
    getSharedStatus, sharedListProjects, observerOptions: SIGNAL_OBSERVER_OPTIONS,
  });

  const statusSettled = statusQuery.isSuccess || statusQuery.isError;
  const listSettled = listQuery.isSuccess || listQuery.isError;
  const settled = statusSettled && (!configured || listSettled);
  const publishedCount = configured ? (listQuery.data?.projects?.length ?? 0) : 0;
  const hasContent = publishedCount > 0;

  return { settled, hasContent, publishedCount };
}
