import { useCallback, useEffect, useRef, useState } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';

/**
 * useSharedProjects — status + project list backing the Projects page
 * "online" sub-tab. Wraps the Task 15 shared-repo API client
 * (getSharedStatus, sharedListProjects, connectShared, refreshShared,
 * pullSharedProject) behind a small local state machine.
 *
 * Refresh-on-entry: the online tab only mounts this hook while it is the
 * active sub-tab (see ProjectsPage.jsx), so a fresh mount really does mean
 * "the user just walked in" -- the very first project-list fetch asks the
 * server to pull the shared repo before listing (`refresh: true`). Every
 * later re-list (after connect, or the explicit refresh button) passes
 * `refresh: false`; the explicit `refresh()` action is what triggers another
 * real remote fetch, via `refreshShared()`.
 *
 * Error handling has two tiers: a failed *initial* load (status or the
 * first list) surfaces `error` since there's nothing to show yet. A failed
 * *refresh* of an already-loaded tab does NOT blank the view -- it flags
 * `stale` so the page can render the "refresh failed, showing results
 * synced <time> ago" banner over the still-valid last-known listing.
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

  // Guards the refresh-on-entry contract: true once this hook instance has
  // issued its first list fetch, so a later relist (post-connect, after a
  // pull) doesn't re-force refresh=1.
  const enteredRef = useRef(false);

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
        const refresh = !enteredRef.current;
        enteredRef.current = true;
        await fetchList(refresh);
      }
    } catch (err) {
      setError(err?.message || 'failed to load shared repository status');
    } finally {
      setLoading(false);
    }
  }, [getSharedStatus, fetchList]);

  useEffect(() => {
    loadStatus();
    // Runs once per mount -- see refresh-on-entry note above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const connect = useCallback(async (nextUrl) => {
    if (connectingRef.current) return; // already connecting -- ignore the repeat click/Enter
    connectingRef.current = true;
    setConnecting(true);
    setConnectError(null);
    try {
      await connectShared(nextUrl);
      // A fresh connection is a fresh "entry" -- force the next list fetch
      // to refresh=1 rather than serving whatever the prior repo's cache was.
      enteredRef.current = false;
      await loadStatus();
    } catch (err) {
      setConnectError(err?.message || 'failed to connect');
    } finally {
      connectingRef.current = false;
      setConnecting(false);
    }
  }, [connectShared, loadStatus]);

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
