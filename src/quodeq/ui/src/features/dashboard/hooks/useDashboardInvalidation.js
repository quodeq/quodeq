import { useCallback, useEffect, useRef } from 'react';
import { projectKeys } from '../../../api/queryKeys.js';

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
    queryClient.invalidateQueries({
      queryKey: projectKeys.project(selectedProject, selectedSource),
      refetchType: 'none',
    });
  }, [queryClient, selectedProject, selectedSource]);

  const refreshDashboardActive = useCallback(() => {
    if (!selectedProject) return;
    queryClient.invalidateQueries({
      queryKey: projectKeys.project(selectedProject, selectedSource),
    });
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
    queryClient.invalidateQueries({
      queryKey: projectKeys.project(selectedProject, selectedSource),
      refetchType: 'none',
    });
    if (reconcileTimer.current) clearTimeout(reconcileTimer.current);
    reconcileTimer.current = setTimeout(() => {
      reconcileTimer.current = null;
      queryClient.invalidateQueries({
        queryKey: projectKeys.project(selectedProject, selectedSource),
      });
    }, 1200);
  }, [queryClient, selectedProject, selectedSource]);
  useEffect(() => () => clearTimeout(reconcileTimer.current), []);

  return scheduleDashboardReconcile;
}

// The three ways useDashboard invalidates the project query subtree, plus
// the debounce ref the third one owns. Extracted verbatim from
// useDashboard.js.
export function useDashboardInvalidation({ queryClient, selectedProject, selectedSource }) {
  const { refreshDashboard, refreshDashboardActive } = useRefreshDashboard({ queryClient, selectedProject, selectedSource });
  const scheduleDashboardReconcile = useScheduleDashboardReconcile({ queryClient, selectedProject, selectedSource });
  return { refreshDashboard, refreshDashboardActive, scheduleDashboardReconcile };
}
