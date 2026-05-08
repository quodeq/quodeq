/**
 * Background refresh while at least one run is in_progress.
 *
 * Mounted from the History page only — we deliberately don't put this
 * on the global score query. Other tabs (Overview, Standards, etc.)
 * shouldn't poll while the user is reading them; the History list is
 * the one place where the user is actively watching for the running
 * row to flip to "complete".
 *
 * When the next refresh sees all runs terminal, the interval clears
 * itself: no runaway polling.
 */
import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { projectKeys } from '../api/queryKeys.js';
import { pollIntervalForRuns } from '../utils/runPolling.js';

export function useRunningRunsRefresh({ selectedProject, availableRuns }) {
  const queryClient = useQueryClient();
  const interval = pollIntervalForRuns(availableRuns);

  useEffect(() => {
    if (!selectedProject || !interval) return undefined;
    const id = setInterval(() => {
      queryClient.invalidateQueries({
        queryKey: projectKeys.project(selectedProject),
      });
    }, interval);
    return () => clearInterval(id);
  }, [queryClient, selectedProject, interval]);
}
