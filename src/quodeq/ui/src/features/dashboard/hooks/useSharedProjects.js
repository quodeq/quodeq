import { useCallback, useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { sharedKeys } from '../../../api/queryKeys.js';

/**
 * useSharedProjects — shared-repo status + project list for the merged
 * Projects page (one list, no tabs -- see ProjectsPage.jsx). Feeds
 * shared-only cards, the toolbar's SyncedIndicator, and -- via
 * useMergedProjects -- every local card's chips/action. Wraps the Task 15
 * shared-repo API client (getSharedStatus, sharedListProjects,
 * connectShared, refreshShared, pullSharedProject) behind two react-query
 * queries (`sharedKeys.status()`, `sharedKeys.list()`) plus a small
 * coalescing refresh.
 *
 * This is the single source of shared status/list data in the app now:
 * usePublish and Settings' SharedRepoSection read (and, on their own
 * mutations, invalidate) these SAME cache entries, so a connect, disconnect,
 * publish, or refresh anywhere in the app is reflected everywhere else
 * through one cache instead of three independently-fetched copies that used
 * to drift apart (audit C6).
 *
 * Cached-first mount: the list query's `queryFn` always passes
 * `refresh: false`, so the UI renders instantly from whatever the server
 * already has cached, never blocking on a synchronous git fetch. Once that
 * cached render lands (the list query's first success), a background
 * `refresh()` kicks off automatically -- exactly once -- to revalidate
 * against the remote, via `refreshShared()`. Every other re-list (after
 * connect, after a publish job completes, or the explicit toolbar refresh
 * button) also passes `refresh: false`; `refreshShared()` is what triggers
 * the real remote fetch.
 *
 * Error handling has two tiers: a failed *initial* load (status, or the
 * first list once configured -- i.e. before either has ever produced data)
 * surfaces `error` since there's nothing to show yet. A failed *refresh* of
 * an already-loaded page does NOT blank the view -- it flags `stale` so the
 * toolbar's SyncedIndicator can show "synced <time> ago · stale" over the
 * still-valid last-known listing.
 *
 * `lastSynced` seeds from the STATUS payload -- the server reports it on
 * every /status response -- so a list-only failure still shows when the
 * repo last synced instead of "not synced yet" (audit B2); once the list
 * has its own envelope, that value overrides it.
 *
 * `refresh()` coalesces rather than drops: a call that arrives while one is
 * already running doesn't start a second POST immediately -- it marks the
 * run as pending and is satisfied by exactly one more round once the
 * current one settles, no matter how many calls stack up in the meantime
 * (audit C3 groundwork; the old in-flight guard used to just silently
 * ignore the repeat call, which is how a post-publish refresh could get
 * dropped on the floor). Both the POST and the follow-up re-list run again
 * invalidating `sharedKeys.all()` -- not just the list -- so `refresh()`
 * doubles as the retry affordance behind the toolbar's "sync failed ·
 * retry" state even when the ORIGINAL failure was the status fetch itself
 * (audit A2): a stuck `configured=false` with no data would otherwise never
 * get another chance, since a disabled list query never fetches on its own.
 */
export function useSharedProjects() {
  const { getSharedStatus, sharedListProjects, connectShared, refreshShared, pullSharedProject } = useApi();
  const queryClient = useQueryClient();

  const statusQuery = useQuery({
    queryKey: sharedKeys.status(),
    queryFn: getSharedStatus,
  });

  const configured = !!statusQuery.data?.configured;

  const listQuery = useQuery({
    queryKey: sharedKeys.list(),
    queryFn: () => sharedListProjects({ refresh: false }),
    enabled: configured,
  });

  const [connecting, setConnecting] = useState(false);
  const [connectError, setConnectError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  // Overridden to true by a failed refresh() round (either the POST or the
  // re-list that follows it); reset on the next round's outcome. Combined
  // with the list envelope's own `stale` flag below -- either can make the
  // toolbar show "· stale".
  const [staleOverride, setStaleOverride] = useState(false);

  // In-flight guards: aria-disabled on the triggering button does not stop
  // a click in this codebase's convention (buttons stay clickable so their
  // handlers can surface a snackbar/tooltip), and the Enter-key path on
  // TermInput bypasses the button entirely. So double-submit protection has
  // to live here, at the hook, rather than on any one caller's button.
  // Refs (not state) because the guard must be readable synchronously on
  // the very next call, before any state update triggered by this call has
  // committed/re-rendered.
  const connectingRef = useRef(false);
  const pullingRef = useRef(false);

  // --- refresh(): coalescing wrapper around one POST + re-list round -----
  // runningRef marks a round actually in flight; pendingRef marks that
  // at least one more caller arrived while it was running and must be
  // satisfied by an EXTRA round once the current one settles; waitersRef
  // holds those callers' resolvers so their returned promise only settles
  // once the round they asked for has actually run.
  const runningRef = useRef(false);
  const pendingRef = useRef(false);
  const waitersRef = useRef([]);

  const refreshCore = useCallback(async () => {
    try {
      await refreshShared();
    } catch {
      // Keep whatever projects/lastSynced are already on screen; just flag
      // it stale. The exact API error message isn't shown here -- the
      // stale banner copy is fixed regardless of cause.
      setStaleOverride(true);
      return;
    }
    try {
      await queryClient.invalidateQueries({ queryKey: sharedKeys.all() });
      const listState = queryClient.getQueryState(sharedKeys.list());
      setStaleOverride(listState?.status === 'error');
    } catch {
      setStaleOverride(true);
    }
  }, [refreshShared, queryClient]);

  const refresh = useCallback(() => {
    if (runningRef.current) {
      pendingRef.current = true;
      return new Promise((resolve) => { waitersRef.current.push(resolve); });
    }
    runningRef.current = true;
    setRefreshing(true);
    return (async () => {
      try {
        await refreshCore();
        // Coalesce: run exactly one more round for every batch of callers
        // that arrived while the previous round was in flight, instead of
        // one round per call.
        while (pendingRef.current) {
          pendingRef.current = false;
          const waiters = waitersRef.current;
          waitersRef.current = [];
          await refreshCore();
          waiters.forEach((resolve) => resolve());
        }
      } finally {
        runningRef.current = false;
        setRefreshing(false);
      }
    })();
  }, [refreshCore]);

  // Background revalidate: fires once, the first time the cached list
  // lands successfully (never when unconfigured, since the list query
  // never runs in that case).
  const bgTriggeredRef = useRef(false);
  useEffect(() => {
    if (listQuery.isSuccess && !bgTriggeredRef.current) {
      bgTriggeredRef.current = true;
      refresh();
    }
  }, [listQuery.isSuccess, refresh]);

  const connect = useCallback(async (nextUrl) => {
    if (connectingRef.current) return; // already connecting -- ignore the repeat click/Enter
    connectingRef.current = true;
    setConnecting(true);
    setConnectError(null);
    try {
      await connectShared(nextUrl);
      // Invalidate everything "shared"-prefixed, not just status: a
      // reconnect to a DIFFERENT url while already configured=true would
      // otherwise never re-fetch the list (its `enabled` flag never
      // toggles, since configured was already true before and after).
      await queryClient.invalidateQueries({ queryKey: sharedKeys.all() });
    } catch (err) {
      setConnectError(err?.message || 'failed to connect');
    } finally {
      connectingRef.current = false;
      setConnecting(false);
    }
  }, [connectShared, queryClient]);

  const pull = useCallback(async (projectId, action) => {
    if (pullingRef.current) return; // a pull is already in flight -- ignore the repeat click
    pullingRef.current = true;
    try {
      const result = await pullSharedProject(projectId, action);
      queryClient.invalidateQueries({ queryKey: sharedKeys.list() });
      return result;
    } finally {
      pullingRef.current = false;
    }
  }, [pullSharedProject, queryClient]);

  const url = statusQuery.data?.url ?? null;
  const projects = listQuery.data?.projects || [];
  const lastSynced = listQuery.data?.lastSynced ?? statusQuery.data?.lastSynced ?? null;
  const stale = staleOverride || !!listQuery.data?.stale;

  // loading: true until BOTH the status query and (when configured) the
  // list query have settled at least once. isLoading (not isPending) is
  // "no data yet AND actively fetching" -- a disabled query is never
  // isLoading, so an unconfigured repo's never-run list query doesn't hold
  // this true forever.
  const loading = statusQuery.isLoading || (configured && listQuery.isLoading);

  // error: only for an INITIAL load failure (no data has ever landed for
  // that query) -- a background refresh failure after data already exists
  // is `stale`, not `error`, so it never blanks an already-working view.
  const statusFailedInitial = statusQuery.isError && statusQuery.data === undefined;
  const listFailedInitial = configured && listQuery.isError && listQuery.data === undefined;
  const error = statusFailedInitial
    ? (statusQuery.error?.message || 'failed to load shared repository status')
    : listFailedInitial
      ? (listQuery.error?.message || 'failed to load shared repository status')
      : null;

  return {
    configured, url, projects, lastSynced, stale,
    loading, error,
    connecting, connectError, connect,
    refreshing, refresh,
    pull,
  };
}
