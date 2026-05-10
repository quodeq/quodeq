/**
 * Polling cadence + predicate for "is any run still alive?".
 *
 * Used by the History page to refresh the run list while at least one
 * run is in progress, so per-dim scores appear in the row as each dim
 * finishes, not only when the umbrella run terminates. Polling is
 * intentionally scoped to the History page (not the global score query)
 * so the rest of the app doesn't fire periodic requests while the user
 * is reading other tabs.
 *
 * 5 seconds: a single dim takes minutes, so 5s catches a dim completion
 * within roughly 5s of it landing on disk -- feels live to the user.
 * Backend cost is small (12 requests/min while a run is alive, none
 * otherwise), and the dim cache is now self-healing (PR #484) so each
 * fetch reflects on-disk truth.
 *
 * The proper next step is per-evaluation SSE (we already have
 * ``useRunEventStream`` for the active job's evaluation pane) so dim
 * updates push to the History row instead of being polled. Until that
 * lands, polling is the simple knob.
 */
export const IN_PROGRESS_POLL_MS = 5000;

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
