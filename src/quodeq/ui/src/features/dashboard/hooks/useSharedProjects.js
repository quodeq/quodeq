import { useCallback, useEffect, useRef, useState } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';

/**
 * useSharedProjects — shared-repo status + project list for the merged
 * Projects page (one list, no tabs -- see ProjectsPage.jsx). Feeds
 * shared-only cards, the toolbar's SyncedIndicator, and -- via
 * useMergedProjects -- every local card's chips/action. Wraps the Task 15
 * shared-repo API client (getSharedStatus, sharedListProjects,
 * connectShared, refreshShared, pullSharedProject) behind a small local
 * state machine.
 *
 * Cached-first mount: the very first project-list fetch always passes
 * `refresh: false` so the UI renders instantly from whatever the server
 * already has cached, never blocking on a synchronous git fetch. Once that
 * cached render lands, a background `refresh()` kicks off automatically
 * (only when a shared repo is configured) to revalidate against the remote,
 * via `refreshShared()`. Every other re-list (after connect, after a publish
 * job completes, or the explicit toolbar refresh button) also passes
 * `refresh: false`; `refreshShared()` is what triggers the real remote
 * fetch.
 *
 * Error handling has two tiers: a failed *initial* load (status or the
 * first list) surfaces `error` since there's nothing to show yet. A failed
 * *refresh* of an already-loaded page does NOT blank the view -- it flags
 * `stale` so the toolbar's SyncedIndicator can show "synced <time> ago ·
 * stale" over the still-valid last-known listing.
 */
export function useSharedProjects() {
  const { getSharedStatus, sharedListProjects, connectShared, refreshShared, pullSharedProject } = useApi();

  const [configured, setConfigured] = useState(false);
  const [url, setUrl] = useState(null);
  const [projects, setProjects] = useState([]);
  const [lastSynced, setLastSynced] = useState(null);
  const [stale, setStale] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [connecting, setConnecting] = useState(false);
  const [connectError, setConnectError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  // In-flight guards: aria-disabled on the triggering button does not stop
  // a click in this codebase's convention (buttons stay clickable so their
  // handlers can surface a snackbar/tooltip), and the Enter-key path on
  // TermInput bypasses the button entirely. So double-submit protection has
  // to live here, at the hook, rather than on any one caller's button.
  // Refs (not state) because the guard must be readable synchronously on
  // the very next call, before any state update triggered by this call has
  // committed/re-rendered.
  const connectingRef = useRef(false);
  const refreshingRef = useRef(false);
  const pullingRef = useRef(false);

  const fetchList = useCallback(async (refresh) => {
    const envelope = await sharedListProjects({ refresh });
    setProjects(envelope?.projects || []);
    setLastSynced(envelope?.lastSynced ?? null);
    setStale(!!envelope?.stale);
    return envelope;
  }, [sharedListProjects]);

  const loadStatus = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getSharedStatus();
      setConfigured(!!data?.configured);
      setUrl(data?.url ?? null);
      if (data?.configured) {
        await fetchList(false);
        return true;
      }
      return false;
    } catch (err) {
      setError(err?.message || 'failed to load shared repository status');
      return false;
    } finally {
      setLoading(false);
    }
  }, [getSharedStatus, fetchList]);

  const refresh = useCallback(async () => {
    if (refreshingRef.current) return; // already refreshing -- ignore the repeat click
    refreshingRef.current = true;
    setRefreshing(true);
    try {
      await refreshShared();
      await fetchList(false);
    } catch {
      // Keep whatever projects/lastSynced are already on screen; just flag
      // it stale. The exact API error message isn't shown here -- the
      // stale banner copy is fixed regardless of cause.
      setStale(true);
    } finally {
      refreshingRef.current = false;
      setRefreshing(false);
    }
  }, [refreshShared, fetchList]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const configuredNow = await loadStatus();
      // Background revalidate: the cached list is already on screen; a failed
      // refresh just flags stale (see refresh()).
      if (configuredNow && !cancelled) refresh();
    })();
    return () => { cancelled = true; };
    // Runs once per mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const connect = useCallback(async (nextUrl) => {
    if (connectingRef.current) return; // already connecting -- ignore the repeat click/Enter
    connectingRef.current = true;
    setConnecting(true);
    setConnectError(null);
    try {
      await connectShared(nextUrl);
      await loadStatus();
    } catch (err) {
      setConnectError(err?.message || 'failed to connect');
    } finally {
      connectingRef.current = false;
      setConnecting(false);
    }
  }, [connectShared, loadStatus]);

  const pull = useCallback(async (projectId, action) => {
    if (pullingRef.current) return; // a pull is already in flight -- ignore the repeat click
    pullingRef.current = true;
    try {
      return await pullSharedProject(projectId, action);
    } finally {
      pullingRef.current = false;
    }
  }, [pullSharedProject]);

  return {
    configured, url, projects, lastSynced, stale,
    loading, error,
    connecting, connectError, connect,
    refreshing, refresh,
    pull,
  };
}
