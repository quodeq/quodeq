/**
 * Keep History data fresh for the user. Two distinct refreshes:
 *
 *   1. On mount — the user just navigated to History. Invalidate once so
 *      the page reflects whatever just happened on disk (e.g. a dim that
 *      finished while they were on another tab). Without this, the user
 *      stares at a stale snapshot until the next poll tick fires.
 *
 *   2. Background polling — while at least one run is in_progress, refresh
 *      on a cadence so the running row flips to "complete" without a
 *      manual reload. When all runs are terminal, the interval clears.
 *
 * Both refreshes are scoped to what History actually renders: the trend and
 * run list (latest scores payload), the latest dashboard, and the dashboard
 * payloads of runs that are still in progress. Completed historical runs are
 * immutable and their caches deliberately frozen (see useDashboard) — a
 * subtree-wide invalidation here would mark every cached run detail stale
 * and reintroduce the background-refetch dim on every pass through History.
 *
 * Mounted from the History page only — we deliberately don't poll on
 * Overview / Standards / etc. The History list is the one place where the
 * user is actively watching for the running row to terminate.
 */
import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { projectKeys } from '../api/queryKeys.js';
import { pollIntervalForRuns } from '../utils/runPolling.js';

const SSE_ENABLED = () => import.meta.env?.VITE_USE_SSE_EVENTS === 'true';

function invalidateHistoryScope(queryClient, selectedProject, availableRuns, selectedSource) {
  queryClient.invalidateQueries({ queryKey: projectKeys.scores(selectedProject, null, selectedSource) });
  queryClient.invalidateQueries({ queryKey: projectKeys.dashboard(selectedProject, null, selectedSource) });
  for (const r of availableRuns || []) {
    if (r?.status === 'in_progress' && r.runId) {
      queryClient.invalidateQueries({ queryKey: projectKeys.dashboard(selectedProject, r.runId, selectedSource) });
    }
  }
}

/**
 * @param {{ selectedProject: string, selectedSource?: 'local'|'shared', availableRuns: Array }} opts
 *
 * selectedSource (default 'local') is folded into every key this hook
 * invalidates so a refresh scoped to one source never marks the other
 * source's cache stale (only local projects ever have in_progress runs, but
 * History can be viewing either source's data when this fires).
 */
export function useRunningRunsRefresh({ selectedProject, selectedSource = 'local', availableRuns }) {
  const queryClient = useQueryClient();
  const interval = pollIntervalForRuns(availableRuns);

  // (1) Mount-time refresh: invalidate once when the project changes (which
  // includes initial mount). The user's act of opening History IS the
  // signal that they want fresh data; don't wait for the polling tick.
  useEffect(() => {
    if (!selectedProject) return;
    invalidateHistoryScope(queryClient, selectedProject, availableRuns, selectedSource);
    // availableRuns is intentionally not a dependency: this refresh fires on
    // navigation (mount) and project switch, not on every runs-list update.
  }, [queryClient, selectedProject, selectedSource]); // eslint-disable-line react-hooks/exhaustive-deps

  // (2) Background polling: only while in_progress runs exist AND SSE is off.
  // With SSE on, terminal-status events drive the running -> terminal flip
  // (see useRunEventStream); polling here would just double the request rate.
  useEffect(() => {
    if (!selectedProject || !interval) return undefined;
    if (SSE_ENABLED()) return undefined;
    const id = setInterval(() => {
      invalidateHistoryScope(queryClient, selectedProject, availableRuns, selectedSource);
    }, interval);
    return () => clearInterval(id);
  }, [queryClient, selectedProject, interval, availableRuns, selectedSource]);
}
