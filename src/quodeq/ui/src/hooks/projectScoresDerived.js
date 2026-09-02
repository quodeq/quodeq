/**
 * useProjectScores.js's pure asOf-resolution and availableRuns-derivation
 * logic, extracted verbatim. Both are still called from inside a useMemo in
 * that hook, so the memoization behavior (and its deps) is unchanged.
 */

// Overview is anchored on completed runs. If selectedRun points at an
// in-progress run (or one that hasn't shown up in availableRuns yet), fall
// back to 'latest' so the cards keep showing the last finished evaluation
// instead of going blank mid-flight. Resolution waits for latestQuery so we
// never fire the scoped query with a stale asOf.
export function resolveAsOf({ isLatestSelection, selectedRun, latestQueryData }) {
  if (isLatestSelection) return null;
  const runs = latestQueryData?.availableRuns;
  if (!runs) return null;
  const match = runs.find((r) => r.runId === selectedRun);
  if (!match) return null;
  if (match.status === "in_progress") return null;
  return selectedRun;
}

export function deriveAvailableRuns({ scoresQueryData, latestQueryData }) {
  const fromPayload =
    scoresQueryData?.availableRuns || latestQueryData?.availableRuns;
  if (fromPayload && fromPayload.length > 0) return fromPayload;
  const trend = scoresQueryData?.trend || latestQueryData?.trend || [];
  return trend.map((row) => ({
    runId: row.runId,
    dateLabel: row.dateLabel || row.runId,
    status: "complete",
  }));
}
