/**
 * Module-level throughput-sample store for the live evaluation stat strip.
 *
 * Samples (`{ t: epoch ms, taken: files done }`) are kept here, keyed by jobId,
 * rather than in component state — so the sliding-window rate SURVIVES a
 * `JobStatStrip` unmount/remount. Navigating out of and back into a running
 * evaluation must not restart the window from empty; doing so blanked the rate
 * to "estimating…" for ~30s on every entry (and tempted a biased whole-run
 * average as a stopgap). The buffer persists for the life of the page; a full
 * reload starts fresh, which is acceptable.
 *
 * No React, no DOM — drop-in testable.
 */

import { RATE_WINDOW_MS } from './buildJobStatCells.js';

const byJob = new Map();

/**
 * Append a sample for a job and trim anything older than RATE_WINDOW_MS.
 * Always keeps at least the newest sample (so a long stall still has a point).
 * @returns {Array<{t:number, taken:number}>} the job's (trimmed) buffer
 */
export function recordRateSample(jobId, t, taken) {
  let buf = byJob.get(jobId);
  if (!buf) { buf = []; byJob.set(jobId, buf); }
  buf.push({ t, taken });
  while (buf.length > 1 && t - buf[0].t > RATE_WINDOW_MS) buf.shift();
  return buf;
}

/** The job's current sample buffer (empty array if none recorded yet). */
export function getRateSamples(jobId) {
  return byJob.get(jobId) || [];
}

/** Test hygiene: the store is module-level and would otherwise leak across tests. */
export function _resetRateSamples() {
  byJob.clear();
}
