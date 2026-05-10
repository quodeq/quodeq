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
 * Mounted from the History page only — we deliberately don't poll on
 * Overview / Standards / etc. The History list is the one place where the
 * user is actively watching for the running row to terminate.
 */
import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { projectKeys } from '../api/queryKeys.js';
import { pollIntervalForRuns } from '../utils/runPolling.js';

const SSE_ENABLED = () => import.meta.env?.VITE_USE_SSE_EVENTS === 'true';

export function useRunningRunsRefresh({ selectedProject, availableRuns }) {
  const queryClient = useQueryClient();
  const interval = pollIntervalForRuns(availableRuns);

  // (1) Mount-time refresh: invalidate once when the project changes (which
  // includes initial mount). The user's act of opening History IS the
  // signal that they want fresh data; don't wait for the polling tick.
  useEffect(() => {
    if (!selectedProject) return;
    queryClient.invalidateQueries({
      queryKey: projectKeys.project(selectedProject),
    });
  }, [queryClient, selectedProject]);

  // (2) Background polling: only while in_progress runs exist AND SSE is off.
  // With SSE on, terminal-status events drive the running -> terminal flip
  // (see useRunEventStream); polling here would just double the request rate.
  useEffect(() => {
    if (!selectedProject || !interval) return undefined;
    if (SSE_ENABLED()) return undefined;
    const id = setInterval(() => {
      queryClient.invalidateQueries({
        queryKey: projectKeys.project(selectedProject),
      });
    }, interval);
    return () => clearInterval(id);
  }, [queryClient, selectedProject, interval]);
}
