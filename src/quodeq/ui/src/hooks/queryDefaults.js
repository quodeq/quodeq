/**
 * Shared react-query defaults.
 *
 * The staleness window lived as a private `STALE_TIME_MS` in useDashboard,
 * usePrefetchRun, useProjectScores and useOpenPrinciple. All four mean the
 * same thing (how long a fetched run payload counts as fresh), so a change in
 * one had to be mirrored by hand in the others or a prefetch and the query it
 * warms would disagree about whether the cache entry still counts.
 */

import { isPendingPayload } from '../api/scoresShape.js';

/** How long a fetched payload stays fresh before react-query refetches it. */
export const STALE_TIME_MS = 60_000;

/** How long an errored query waits before trying the server again. */
export const ERROR_RETRY_MS = 15_000;

/**
 * refetchInterval that turns a failed query into a self-healing one.
 *
 * The client's recovery paths assume a browser: refetchOnWindowFocus fires
 * when the user tabs back, refetchOnReconnect when the network returns. The
 * desktop webview has neither signal, its window never blurs, so a query
 * that exhausted its retries (for example against a server still warming
 * its score caches) stayed in error state forever and the Overview parked
 * on "Couldn't load this project" until a full navigation away and back.
 *
 * Polling only while the query holds an error keeps the cost at zero for
 * healthy queries: the moment a refetch succeeds the interval turns off and
 * staleTime governs freshness again. Frozen queries (staleTime: Infinity)
 * are unaffected while they hold data, and get the same recovery when a
 * background refetch of them fails.
 */
export const refetchWhileError = (query) => (query.state.error ? ERROR_RETRY_MS : false);

/** How often a query re-asks for a payload the server reported as still warming. */
export const WARMUP_POLL_MS = 3000;

/**
 * refetchWhileError, plus polling while the payload is the server's pending
 * body (`{ pending: true, warmup }`, see api/scoresShape.js isPendingPayload).
 *
 * At boot, or after an upgrade invalidated the score caches, the Overview
 * routes answer 202 pending while the server's warm-up still owes the
 * project, instead of building a large project inline beside the worker
 * until the client gave up. The query keeps the pending body as data (so it
 * is loading, not an error) and polls until the real payload replaces it;
 * the interval turns off the moment it does.
 */
export const refetchWhilePendingOrError = (query) =>
  (isPendingPayload(query.state.data) ? WARMUP_POLL_MS : refetchWhileError(query));
