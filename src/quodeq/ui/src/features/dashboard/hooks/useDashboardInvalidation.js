import { useCallback, useEffect, useRef } from 'react';
import { projectKeys } from '../../../api/queryKeys.js';

// Coalesces rapid multi-dismiss/restore bursts into one refetch instead of
// one per action (see useScheduleDashboardReconcile below).
const RECONCILE_DEBOUNCE_MS = 1200;

// Invalidation option that marks the project's queries stale without
// refetching the mounted observers now (see refreshDashboard below).
const MARK_STALE_ONLY = { refetchType: 'none' };

// Invalidate the selected project's query subtree. With no options the
// active observers refetch now; MARK_STALE_ONLY defers that to the next mount.
function invalidateProject(queryClient, selectedProject, selectedSource, options) {
  queryClient.invalidateQueries({
    queryKey: projectKeys.project(selectedProject, selectedSource),
    ...options,
  });
}

// The per-run arrays a project payload can carry (dashboard: trend,
// partialRuns; scores: trend, availableRuns). History rows and the run
// navigator are derived from these, so dropping a run here removes it
// from every view at once, before the rollup refetch lands.
const RUN_LIST_KEYS = ['trend', 'partialRuns', 'availableRuns'];

function withoutRun(data, runId) {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return data;
  let changed = false;
  const next = { ...data };
  for (const key of RUN_LIST_KEYS) {
    if (!Array.isArray(data[key])) continue;
    const kept = data[key].filter((entry) => entry?.runId !== runId);
    if (kept.length !== data[key].length) { next[key] = kept; changed = true; }
  }
  return changed ? next : data;
}

/**
 * Drop *runId* from every run list cached under the project subtree.
 *
 * Fetches in flight under the project are cancelled first, so a reply that
 * left the server before the delete cannot land afterwards and put the run
 * back (the reconcile that follows refetches anyway). Only queries whose
 * data actually changes are written: a blanket setQueriesData would mark
 * every query in the subtree fresh, which would silently undo an
 * invalidation made just before and pin the staleTime:Infinity ones.
 */
export function dropRunFromProjectQueries(queryClient, projectId, source, runId) {
  const queryKey = projectKeys.project(projectId, source);
  queryClient.cancelQueries({ queryKey });
  for (const [key, data] of queryClient.getQueriesData({ queryKey })) {
    const next = withoutRun(data, runId);
    if (next !== data) queryClient.setQueryData(key, next);
  }
}

// refreshDashboard: mark project queries stale but DON'T trigger an
// immediate refetch. The dashboard payload is 10-20 MB on large projects
// (one run's full violation + compliance arrays × multiple dimensions);
// refetching on every dismiss froze the UI for 1-3 s while the browser
// parsed the JSON and React re-rendered. The dismiss POST already returned
// the rescored run for the active page (PrincipleDetail / FileDetail /
// FindingDetail) to apply locally — the dashboard rollup just needs to be
// eventually-correct, which React Query handles automatically:
// ``refetchType: 'none'`` marks the cache stale, the next mount refetches
// naturally on navigation.
//
// refreshDashboardActive: force-refresh variant for when fresh data is
// genuinely expected NOW and the user is parked on a mounted observer that
// won't otherwise refetch — namely when an evaluation finishes. Unlike
// refreshDashboard (refetchType:'none', used by the high-frequency dismiss
// path to avoid re-pulling the 10-20 MB payload), this uses the default
// refetchType:'active' so the always-mounted Overview observer actually
// refetches. Without it, a freshly-completed run leaves the Overview
// showing the stale pre-run payload (empty "No evaluations yet" state)
// until the user switches projects and back, which is the only other
// action that re-subscribes the observer to its query key.
function useRefreshDashboard({ queryClient, selectedProject, selectedSource }) {
  const refreshDashboard = useCallback(() => {
    if (!selectedProject) return;
    invalidateProject(queryClient, selectedProject, selectedSource, MARK_STALE_ONLY);
  }, [queryClient, selectedProject, selectedSource]);

  const refreshDashboardActive = useCallback(() => {
    if (!selectedProject) return;
    invalidateProject(queryClient, selectedProject, selectedSource);
  }, [queryClient, selectedProject, selectedSource]);

  return { refreshDashboard, refreshDashboardActive };
}

// Debounced counterpart to refreshDashboardActive, for the high-frequency
// suppression mutations (dismiss/restore/delete). refreshDashboard's
// refetchType:'none' leaves the Overview's always-mounted observer showing
// stale data until the user switches projects and back -- fine for a single
// dismiss (the mutation response already patched the visible page's local
// scores via applyMutationDelta), but restore-all/delete-all return a
// payload the delta gates can't apply (scores:null, delta.isLatest:false),
// so the Overview stays wrong indefinitely. The pywebview desktop window
// also never fires the focus-refetch a browser tab would get on refocus,
// so there's no other path back to fresh data short of an app switch.
// Debounce coalesces rapid multi-dismiss/restore bursts into one refetch of
// the (potentially 10-20 MB) dashboard payload instead of one per action.
function useScheduleDashboardReconcile({ queryClient, selectedProject, selectedSource }) {
  const reconcileTimer = useRef(null);
  const scheduleDashboardReconcile = useCallback(() => {
    if (!selectedProject) return;
    // Mark-stale NOW, synchronously, before the timer is (re)armed. The
    // timer is a single shared ref, cleared on unmount and re-armed by the
    // next schedule call; if the ACTIVE refetch below ever gets dropped
    // (unmount) or fires against a stale closure (the project switched
    // before the 1200ms elapsed, so it invalidates the old project's now
    // inactive queries -- a harmless no-op), this mark-stale has already
    // happened, so the mutation degrades to refreshDashboard's
    // mark-stale-only semantics and a remount or Overview-return still
    // self-heals.
    invalidateProject(queryClient, selectedProject, selectedSource, MARK_STALE_ONLY);
    if (reconcileTimer.current) clearTimeout(reconcileTimer.current);
    reconcileTimer.current = setTimeout(() => {
      reconcileTimer.current = null;
      invalidateProject(queryClient, selectedProject, selectedSource);
    }, RECONCILE_DEBOUNCE_MS);
  }, [queryClient, selectedProject, selectedSource]);
  useEffect(() => () => clearTimeout(reconcileTimer.current), []);

  return scheduleDashboardReconcile;
}

/**
 * The three ways useDashboard invalidates the project query subtree, plus
 * the debounce ref the third one owns.
 */
export function useDashboardInvalidation({ queryClient, selectedProject, selectedSource }) {
  const { refreshDashboard, refreshDashboardActive } = useRefreshDashboard({ queryClient, selectedProject, selectedSource });
  const scheduleDashboardReconcile = useScheduleDashboardReconcile({ queryClient, selectedProject, selectedSource });
  const dropRunFromCache = useCallback((runId) => {
    if (!selectedProject) return;
    dropRunFromProjectQueries(queryClient, selectedProject, selectedSource, runId);
  }, [queryClient, selectedProject, selectedSource]);
  return { refreshDashboard, refreshDashboardActive, scheduleDashboardReconcile, dropRunFromCache };
}
