/**
 * Shared react-query defaults.
 *
 * The staleness window lived as a private `STALE_TIME_MS` in useDashboard,
 * usePrefetchRun, useProjectScores and useOpenPrinciple. All four mean the
 * same thing (how long a fetched run payload counts as fresh), so a change in
 * one had to be mirrored by hand in the others or a prefetch and the query it
 * warms would disagree about whether the cache entry still counts.
 */

/** How long a fetched payload stays fresh before react-query refetches it. */
export const STALE_TIME_MS = 60_000;
