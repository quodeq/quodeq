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
