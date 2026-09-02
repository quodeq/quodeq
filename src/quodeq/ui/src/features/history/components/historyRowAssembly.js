// Row-assembly helpers shared by HistoryPage.jsx (which re-exports
// assembleHistoryRows/visibleHistoryRows -- see HistoryPage.stubs.test.jsx)
// and HistoryContent.jsx/EvaluationsTable.jsx. Extracted verbatim from
// HistoryPage.jsx; split into its own module (rather than left inline) so
// HistoryContent.jsx can read HIDDEN_STATUSES without importing back from
// HistoryPage.jsx (which would create a circular import, since HistoryPage
// imports HistoryContent).

// Only outright failures are hidden. Cancelled runs may still have written
// per-dim evaluation files (the dashboard's overview reads them and shows
// scores), so hiding them here would create a confusing mismatch where the
// overview shows scores from a run that history claims doesn't exist.
export const HIDDEN_STATUSES = new Set(['failed']);
export const PARTIAL_STATUSES = new Set(['cancelled']);

function buildInProgressStubs(availableRuns, trend) {
  const trendIds = new Set((trend || []).map((e) => e.runId));
  return (availableRuns || [])
    .filter((r) => r.status === 'in_progress' && !trendIds.has(r.runId))
    // hasScoredDims=false: this run is running but no dimension has finished
    // scoring yet. Clicking would land on an empty dashboard, so the row is
    // rendered as not-yet-ready.
    .map((r) => ({ runId: r.runId, dateLabel: r.dateLabel, dateISO: null, status: 'in_progress', hasScoredDims: false }));
}

function buildCancelledStubs(availableRuns, trend) {
  // Cancelled runs are stripped from `trend` server-side (they're not chart
  // points), but their kept-findings scores still drive the Overview when no
  // complete run exists. Surface them as partial, dated rows so History and
  // the Overview agree instead of showing scores over an empty table.
  const trendIds = new Set((trend || []).map((e) => e.runId));
  return (availableRuns || [])
    .filter((r) => r.status === 'cancelled' && !trendIds.has(r.runId))
    .map((r) => ({
      runId: r.runId, dateLabel: r.dateLabel, dateISO: r.dateISO ?? null,
      status: 'cancelled', hasScoredDims: true,
    }));
}

/**
 * Ordered rows for the History table: in-progress runs on top (running now),
 * then cancelled partial rows interleaved with the (already newest-first)
 * trend by date. Cancelled runs are absent from `trend`, so without this a
 * project whose only runs are cancelled shows an empty History while the
 * Overview shows their scores.
 */
export function assembleHistoryRows(availableRuns, trend) {
  const inProgress = buildInProgressStubs(availableRuns, trend);
  const cancelled = buildCancelledStubs(availableRuns, trend);
  const dated = [...cancelled, ...(trend || [])].sort(
    (a, b) => (b.dateISO || '').localeCompare(a.dateISO || ''),
  );
  return [...inProgress, ...dated];
}

/**
 * Assembled rows minus hidden (failed) runs — the rows the table actually
 * shows. The "no evaluations yet" guard checks this (not just `trend`), so
 * a project whose only runs are cancelled still populates History instead
 * of short-circuiting to empty while the Overview shows their scores.
 */
export function visibleHistoryRows(availableRuns, trend) {
  const statusById = new Map((availableRuns || []).map((r) => [r.runId, r.status]));
  return assembleHistoryRows(availableRuns, trend).filter(
    (r) => !HIDDEN_STATUSES.has(statusById.get(r.runId) ?? r.status),
  );
}
