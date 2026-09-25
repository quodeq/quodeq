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
 */

import { createDimension } from './dimension.js';

/**
 * Create a canonical Dashboard from a raw API response.
 *
 * @param {Object} raw
 * @returns {Dashboard}
 */
export function createDashboard(raw) {
  if (!raw || typeof raw !== 'object') return raw;
  return {
    dimensions: (raw.dimensions || []).map(createDimension),
    trend: raw.trend,
    partialRuns: raw.partialRuns || [],
    selectedRun: raw.selectedRun,
  };
}
