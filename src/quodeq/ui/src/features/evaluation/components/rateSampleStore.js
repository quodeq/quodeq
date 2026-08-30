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

/**
 * Build an independent throughput-sample store: append/read/reset closing
 * over its own per-job buffer map. `windowMs` decouples the trim rule from
 * RATE_WINDOW_MS for tests; production code shares one default instance.
 */
export function createRateSampleStore({ windowMs = RATE_WINDOW_MS } = {}) {
  const byJob = new Map();

  /**
   * Append a sample for a job and trim anything older than windowMs.
   * Always keeps at least the newest sample (so a long stall still has a point).
   * @returns {Array<{t:number, taken:number}>} the job's (trimmed) buffer
   */
  function recordRateSample(jobId, t, taken) {
    let buf = byJob.get(jobId);
    if (!buf) { buf = []; byJob.set(jobId, buf); }
    buf.push({ t, taken });
    while (buf.length > 1 && t - buf[0].t > windowMs) buf.shift();
    return buf;
  }

  /** The job's current sample buffer (empty array if none recorded yet). */
  function getRateSamples(jobId) {
    return byJob.get(jobId) || [];
  }

  /** Test hygiene: the store is otherwise long-lived and would leak across tests. */
  function reset() {
    byJob.clear();
  }

  return { recordRateSample, getRateSamples, reset };
}

/** The app-wide throughput store every production import shares. */
export const defaultRateSampleStore = createRateSampleStore();

export function recordRateSample(jobId, t, taken) {
  return defaultRateSampleStore.recordRateSample(jobId, t, taken);
}

export function getRateSamples(jobId) {
  return defaultRateSampleStore.getRateSamples(jobId);
}

/** Test hygiene: the store is module-level and would otherwise leak across tests. */
export function _resetRateSamples() {
  defaultRateSampleStore.reset();
}
