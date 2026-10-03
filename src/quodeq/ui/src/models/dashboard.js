/**
 * Dashboard response model — the full response from GET /projects/{id}/dashboard.
 *
 * @typedef {import('./dimension.js').Dimension} Dimension
 *
 * @typedef {Object} TrendEntry
 * @property {string} runId
 * @property {string} dateLabel
 *
 * @typedef {Object} Dashboard
 * @property {Dimension[]}   dimensions
 * @property {TrendEntry[]}  trend
 * @property {TrendEntry[]}  partialRuns  cancelled runs with their own scores; History rows only, never chart points
 * @property {Object|null}   selectedRun
 * @property {Object}        sinceBaseline  per-dimension since-baseline summary from the backend; {} while the run is not terminal
 */

import { createDimension, createSlimDimension } from './dimension.js';

const EMPTY_TREND = Object.freeze([]);

/**
 * Create a canonical Dashboard from a raw API response.
 *
 * @param {Object} raw
 * @returns {Dashboard}
 */
export function createDashboard(raw) {
  if (!raw || typeof raw !== 'object') return raw;
  return {
    // A dimension without a violations key is the overview shape: keep its
    // bodies absent (createDimension would coerce them to [], which reads
    // as "zero findings" to the run views and the map).
    dimensions: (raw.dimensions || []).map((d) => (d && !('violations' in d) ? createSlimDimension(d) : createDimension(d))),
    trend: raw.trend || EMPTY_TREND,
    partialRuns: raw.partialRuns || [],
    selectedRun: raw.selectedRun,
    sinceBaseline: raw.sinceBaseline || {},
  };
}
