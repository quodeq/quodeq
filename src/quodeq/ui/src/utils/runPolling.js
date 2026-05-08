/**
 * Polling cadence + predicate for "is any run still alive?".
 *
 * Used by the History page to refresh the run list while at least one
 * run is in progress, so the row's running indicator and the
 * overview pick up the freshly-completed dims without the user
 * manually refreshing. Polling is intentionally scoped to the History
 * page (not the global score query) so the rest of the app doesn't
 * fire periodic requests while the user is reading other tabs.
 *
 * 15 seconds: a finishing run takes minutes, so 15s is plenty tight
 * to update the row visibly soon after the umbrella run terminates,
 * while keeping background load near-zero (4 requests/min while a
 * run is alive, none otherwise).
 */
export const IN_PROGRESS_POLL_MS = 15000;

/**
 * Return the poll interval for `useQuery.refetchInterval`, or `false`
 * to disable polling entirely.
 *
 * @param {Array<{ status?: string }> | null | undefined} availableRuns
 * @returns {number | false}
 */
export function pollIntervalForRuns(availableRuns) {
  if (!availableRuns || availableRuns.length === 0) return false;
  const anyRunning = availableRuns.some((r) => r && r.status === 'in_progress');
  return anyRunning ? IN_PROGRESS_POLL_MS : false;
}
