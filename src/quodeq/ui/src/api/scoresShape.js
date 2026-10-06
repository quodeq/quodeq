/**
 * Shared request/response shaping for the scores endpoints.
 *
 * The local (`/projects/...`) and shared (`/shared/projects/...`) score
 * routes serve the same payloads from different roots, so the query-string
 * building and the raw-to-model mapping live here once instead of being
 * copied into both clients.
 */

import { createDimension, createSlimDimension } from '../models/dimension.js';

/**
 * Build the optional `?asOf=` query string for a scores request.
 * @param {string|null} [asOfRun] Run id to pin the response to, or null/'' for latest.
 * @returns {string} `?asOf=<encoded run id>`, or '' when no run is given.
 */
export function asOfQuery(asOfRun) {
  return asOfRun ? `?asOf=${encodeURIComponent(asOfRun)}` : '';
}

/**
 * Build the optional `?run=` query string for a dashboard request.
 * @param {string|null} [run] Run id to fetch, or null/'' for the server default.
 * @returns {string} `?run=<encoded run id>`, or '' when no run is given.
 */
export function runQuery(run) {
  return run ? `?run=${encodeURIComponent(run)}` : '';
}

/**
 * The query string of a /compliance-detail request. `run` scopes it to one
 * run's deferred lists and wins over `asOf`, which scopes the accumulated ones.
 * @param {{kind: string, dimension: string, run?: string|null, asOf?: string|null, principle?: string, pathPrefix?: string}} scope
 * @returns {string} Without the leading `?`.
 */
export function findingDetailQuery({ kind, dimension, run, asOf, principle, pathPrefix }) {
  const params = new URLSearchParams({ dimension, kind });
  if (run) params.set('run', run);
  else if (asOf) params.set('asOf', asOf);
  if (principle) params.set('principle', principle);
  if (pathPrefix) params.set('pathPrefix', pathPrefix);
  return params.toString();
}

/**
 * True for the body the Overview routes answer 202 with while the server's
 * warm-up still owes the project its caches: `{ pending: true, warmup }`.
 * Fetchers hand it through untouched (a model built from it would read as an
 * empty project) and the hooks poll on it; see hooks/queryDefaults.js.
 * @param {Object|null|undefined} data
 * @returns {boolean}
 */
export function isPendingPayload(data) {
  return data?.pending === true;
}

/**
 * Map the `dimensions` array of an accumulated payload to Dimension models.
 * @param {Object} data Raw accumulated payload; left untouched when it has no dimensions array.
 * @returns {Object} The same payload object.
 */
export function parseAccumulated(data) {
  if (Array.isArray(data?.dimensions)) {
    data.dimensions = data.dimensions.map(createDimension);
  }
  return data;
}

/**
 * Map the `accumulated.dimensions` array of a unified scores payload to Dimension models.
 * @param {Object} data Raw unified scores payload; left untouched when it has no accumulated dimensions.
 * @returns {Object} The same payload object.
 */
export function parseUnifiedScores(data) {
  if (data?.accumulated && Array.isArray(data.accumulated.dimensions)) {
    data.accumulated.dimensions = data.accumulated.dimensions.map(createDimension);
  }
  return data;
}

/**
 * Parse a fleet compare response: every summary's slim dimensions, the
 * per-project errors untouched.
 */
export function parseFleetCompare(data) {
  return {
    summaries: (data?.summaries || []).map(parseSlimDimensions),
    errors: data?.errors || {},
  };
}

/**
 * Map the `dimensions` array of a slim payload (run scores, compare summary)
 * to SlimDimension models.
 * @param {Object} data Raw slim payload; left untouched when it has no dimensions array.
 * @returns {Object} The same payload object.
 */
export function parseSlimDimensions(data) {
  if (Array.isArray(data?.dimensions)) {
    data.dimensions = data.dimensions.map(createSlimDimension);
  }
  return data;
}
