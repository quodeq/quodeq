// Row-assembly helpers shared by HistoryPage.jsx (which re-exports
// assembleHistoryRows/visibleHistoryRows -- see HistoryPage.stubs.test.jsx)
// and HistoryContent.jsx/EvaluationsTable.jsx. Extracted verbatim from
// HistoryPage.jsx; split into its own module (rather than left inline) so
// HistoryContent.jsx can read HIDDEN_STATUSES without importing back from
// HistoryPage.jsx (which would create a circular import, since HistoryPage
// imports HistoryContent).

import { RUN_STATE } from '../../../vocab/runState.js';

// Only outright failures are hidden. A cancelled run that scored something
// is listed from `partialRuns` with its own values (see assembleHistoryRows).
export const HIDDEN_STATUSES = new Set([RUN_STATE.FAILED]);
export const PARTIAL_STATUSES = new Set([RUN_STATE.CANCELLED]);

function buildInProgressStubs(availableRuns, trendIds) {
  return (availableRuns || [])
    .filter((r) => r.status === RUN_STATE.RUNNING && !trendIds.has(r.runId))
    // hasScoredDims=false: this run is running but no dimension has finished
    // scoring yet. Clicking would land on an empty dashboard, so the row is
    // rendered as not-yet-ready.
    .map((r) => ({ runId: r.runId, dateLabel: r.dateLabel, dateISO: null, status: RUN_STATE.RUNNING, hasScoredDims: false }));
}

/**
 * Ordered rows for the History table: in-progress runs on top (running now),
 * then the trend and the partial runs interleaved by date, newest first.
 *
 * `partialRuns` are the cancelled runs that scored at least one dimension,
 * with the run's own grade and score (the server keeps them out of `trend`,
 * so they are never chart points and never move an accumulated number). A
 * cancelled run with nothing scored has no row: there is nothing to open.
 */
export function assembleHistoryRows(availableRuns, trend, partialRuns = []) {
  const trendIds = new Set((trend || []).map((e) => e.runId));
  const inProgress = buildInProgressStubs(availableRuns, trendIds);
  const partial = (partialRuns || []).filter((e) => !trendIds.has(e.runId));
  const dated = [...partial, ...(trend || [])].sort(
    (a, b) => (b.dateISO || '').localeCompare(a.dateISO || ''),
  );
  return [...inProgress, ...dated];
}

/**
 * Assembled rows minus hidden (failed) runs — the rows the table actually
 * shows. The "no evaluations yet" guard checks this (not just `trend`), so
 * a project whose only runs are cancelled still populates History from its
 * partial runs instead of short-circuiting to empty while the Overview
 * shows their scores.
 */
export function visibleHistoryRows(availableRuns, trend, partialRuns = []) {
  const statusById = new Map((availableRuns || []).map((r) => [r.runId, r.status]));
  return assembleHistoryRows(availableRuns, trend, partialRuns).filter(
    (r) => !HIDDEN_STATUSES.has(statusById.get(r.runId) ?? r.status),
  );
}
