import { useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { invalidateProjects } from './invalidateProjects.js';
import { LATEST_RUN_ID } from '../constants.js';

/** The Overview's run selection after *runId* is deleted. */
export function nextSelectedRunAfterDelete(selectedRun, runId) {
  return selectedRun === runId ? LATEST_RUN_ID : selectedRun;
}

/**
 * The app-level reaction to a run deleted from History: drop it from every
 * cached run list now (the rollup refetch is debounced and pulls the whole
 * dashboard), move a selection that pointed at it, then the same reconcile
 * dismiss/restore use, plus a project-list refetch for the cards' run counts.
 */
export function useHandleRunDeleted({
  dropRunFromCache, setSelectedRun, historySelectedRun, setHistorySelectedRun, scheduleDashboardReconcile,
}) {
  const queryClient = useQueryClient();
  return useCallback((runId) => {
    dropRunFromCache(runId);
    setSelectedRun((current) => nextSelectedRunAfterDelete(current, runId));
    if (historySelectedRun === runId) setHistorySelectedRun(LATEST_RUN_ID);
    scheduleDashboardReconcile();
    invalidateProjects(queryClient).catch((err) => console.warn('[runDeletion] project list refetch failed:', err));
  }, [dropRunFromCache, setSelectedRun, historySelectedRun, setHistorySelectedRun, scheduleDashboardReconcile, queryClient]);
}
