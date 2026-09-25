/**
 * Shared-repo status and project list for the merged Projects page (one list,
 * no tabs -- see ProjectsPage.jsx). Feeds the shared-only cards, the toolbar's
 * SyncedIndicator, and -- through useMergedProjects -- every local card's
 * chips and action. It wraps the shared-repo API client (getSharedStatus,
 * sharedListProjects, connectShared, refreshShared, pullSharedProject) behind
 * two react-query queries (`sharedKeys.status()`, `sharedKeys.list()`) plus a
 * small coalescing refresh.
 *
 * This module is the app's single source of shared status/list data: usePublish
 * and Settings' SharedRepoSection read, and on their own mutations invalidate,
 * these SAME cache entries, so a connect, disconnect, publish or refresh
 * anywhere is reflected everywhere through one cache rather than three
 * independently fetched copies that used to drift apart.
 *
 * Cached-first mount: the list query's `queryFn` always passes
 * `refresh: false`, so the UI renders instantly from whatever the server has
 * cached and never blocks on a synchronous git fetch. Once that cached render
 * lands, a background `refresh()` kicks off automatically, exactly once, to
 * revalidate against the remote. Every other re-list (after connect, after a
 * publish job completes, or the explicit toolbar refresh button) also passes
 * `refresh: false`; `refreshShared()` is what triggers the real remote fetch.
 *
 * Error handling has two tiers. A failed *initial* load (status, or the first
 * list once configured, i.e. before either has ever produced data) surfaces
 * `error`, since there is nothing to show yet. A failed *refresh* of an
 * already-loaded page does NOT blank the view: it flags `stale` so the
 * toolbar's SyncedIndicator can show "synced <time> ago - stale" over the
 * still-valid last-known listing.
 *
 * `lastSynced` seeds from the STATUS payload, which the server reports on
 * every /status response, so a list-only failure still shows when the repo
 * last synced instead of "not synced yet"; once the list has its own
 * envelope, that value overrides it.
 *
 * `refresh()` coalesces rather than drops: a call arriving while one is
 * already running does not start a second POST, it marks the run pending and
 * is satisfied by exactly one more round once the current one settles, no
 * matter how many calls stack up. Both the POST and the follow-up re-list
 * invalidate `sharedKeys.all()`, not just the list, so `refresh()` doubles as
 * the retry affordance behind the toolbar's "sync failed - retry" state even
 * when the original failure was the status fetch itself: a stuck
 * `configured=false` with no data would otherwise never get another chance,
 * because a disabled list query never fetches on its own.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { sharedKeys } from '../../../api/queryKeys.js';
import { t } from '../../../strings/index.js';
import { useCoalescedRefresh } from './useCoalescedRefresh.js';
import { useSharedActions } from './useSharedActions.js';
import { useSharedStatusAndList } from './useSharedStatusAndList.js';

// react-query's own query-state status ('pending'|'error'|'success'), not
// the run/job/dim vocabulary -- kept local rather than forced into vocab/*.js.
const QUERY_STATUS_ERROR = 'error';

// One refresh round: POST, then let the caller re-list. Failures keep the
// page's data and flag it stale instead of rejecting.
function makeRefreshCore({ refreshShared, queryClient, setStaleOverride }) {
  return async () => {
    try {
      await refreshShared();
    } catch (err) {
      // Keep whatever projects/lastSynced are already on screen; just flag
      // it stale. The exact API error message isn't shown here -- the
      // stale banner copy is fixed regardless of cause.
      console.warn('[useSharedProjects] refresh failed:', err);
      setStaleOverride(true);
      return;
    }
    try {
      await queryClient.invalidateQueries({ queryKey: sharedKeys.all() });
      const listState = queryClient.getQueryState(sharedKeys.list());
      setStaleOverride(listState?.status === QUERY_STATUS_ERROR);
    } catch (err) {
      console.warn('[useSharedProjects] post-refresh invalidate failed:', err);
      setStaleOverride(true);
    }
  };
}

/**
 * Message for an INITIAL load failure, meaning no data has ever landed for
 * that query. A background refresh failure after data already exists is
 * `stale`, not `error`, so it never blanks an already-working view.
 */
function deriveSharedError({ statusQuery, listQuery, configured }) {
  if (statusQuery.isError && statusQuery.data === undefined) {
    return statusQuery.error?.message || t('projects.sharedStatusFailed');
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
function deriveSharedFreshness({ statusQuery, listQuery, configured, staleOverride }) {
  return {
    stale: staleOverride || !!listQuery.data?.stale,
    loading: statusQuery.isLoading || (configured && listQuery.isLoading),
  };
}

function deriveSharedProjectsState({ statusQuery, listQuery, configured, staleOverride }) {
  const url = statusQuery.data?.url ?? null;
  // Gated on `configured`, not just read off listQuery.data: the list query
  // is disabled (not removed) when unconfigured, so a lingering cache entry
  // from before a disconnect (or from a DIFFERENT shared repo before a
  // reconnect) would otherwise keep rendering shared cards -- with live pull
  // buttons -- on a page that has nothing connected (ghost shared cards
  // after disconnect).
  const projects = configured ? (listQuery.data?.projects || []) : [];
  const lastSynced = listQuery.data?.lastSynced ?? statusQuery.data?.lastSynced ?? null;
  return {
    url,
    projects,
    lastSynced,
    ...deriveSharedFreshness({ statusQuery, listQuery, configured, staleOverride }),
    error: deriveSharedError({ statusQuery, listQuery, configured }),
  };
}

// Background revalidate: fires once, the first time the cached list lands
// successfully (never when unconfigured, since the list query never runs in
// that case).
function useBackgroundRevalidate(listQuerySuccess, refresh) {
  const bgTriggeredRef = useRef(false);
  useEffect(() => {
    if (listQuerySuccess && !bgTriggeredRef.current) {
      bgTriggeredRef.current = true;
      // No .catch needed here or at the toolbar's onRefresh: refreshCore
      // (makeRefreshCore above) catches both of its phases and reports
      // failure through setStaleOverride, so the promise refresh() returns
      // never rejects. useCoalescedRefresh's waiter rejection only surfaces
      // a refreshCore throw, which this core cannot produce.
      refresh();
    }
  }, [listQuerySuccess, refresh]);
}

/**
 * The shared-repo screen's data and actions: whether sharing is configured,
 * the remote project list and its freshness, plus connect, refresh and pull.
 *
 * A refresh is one POST followed by a re-list, coalesced so concurrent callers
 * share a single round; a failed round marks the list stale rather than
 * rejecting, so the toolbar shows "stale" instead of an error.
 */
export function useSharedProjects() {
  const { getSharedStatus, sharedListProjects, connectShared, refreshShared, pullSharedProject } = useApi();
  const queryClient = useQueryClient();

  const { statusQuery, configured, listQuery } = useSharedStatusAndList({ getSharedStatus, sharedListProjects });

  // Overridden to true by a failed refresh() round (either the POST or the
  // re-list that follows it); reset on the next round's outcome. Combined
  // with the list envelope's own `stale` flag below -- either can make the
  // toolbar show "· stale".
  const [staleOverride, setStaleOverride] = useState(false);

  // connect()/pull(): see useSharedActions -- same in-flight-ref idiom as
  // usePublishTrigger.
  const { connecting, connectError, connect, pull } = useSharedActions({ connectShared, pullSharedProject, queryClient });

  const refreshCore = useCallback(
    makeRefreshCore({ refreshShared, queryClient, setStaleOverride }),
    [refreshShared, queryClient],
  );

  // refresh(): coalescing wrapper around one POST + re-list round (see
  // useCoalescedRefresh).
  const { refreshing, refresh } = useCoalescedRefresh(refreshCore);

  useBackgroundRevalidate(listQuery.isSuccess, refresh);

  const { url, projects, lastSynced, stale, loading, error } = deriveSharedProjectsState({
    statusQuery, listQuery, configured, staleOverride,
  });

  return {
    configured, url, projects, lastSynced, stale,
    loading, error,
    connecting, connectError, connect,
    refreshing, refresh,
    pull,
  };
}

// This signal feeds a one-time startup decision (wizard auto-open, initial
// landing). Focus revalidation belongs to the pages that render the list, not
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
 * background refresh, no mutations, and no error surface: a failed status
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
  const hasContent = configured && (listQuery.data?.projects?.length ?? 0) > 0;

  return { settled, hasContent };
}
