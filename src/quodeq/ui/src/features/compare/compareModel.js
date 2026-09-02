/**
 * Pure view-model builders for the Compare tab.
 *
 * Everything here is plain data-in/data-out so the fleet aggregation,
 * consequence ranking and dimension drill-down can be unit tested without
 * mounting React. Inputs are the Project models from /api/projects plus one
 * compare-summary payload per project (see services/compare.py); nothing in
 * this module fetches.
 *
 * This module keeps the shared primitives (parsing, keying, standards
 * filtering, date math, trend deltas, small numeric helpers) and re-exports
 * everything from the split-out builders below, so `compareModel.js` stays
 * the one import path every caller and compareModel.test.js already use:
 *   - compareFleet.js           fleet-table rows + fleet-level aggregates
 *   - compareBoard.js           cross-project dimension board + attention
 *   - compareDuel.js            head-to-head duel view
 *   - compareDimensionView.js   single-dimension drill-down
 */

import {
  filterTrendByVisibleStandards,
  filterAccumulatedByVisibleStandards,
} from '../../utils/scoreFiltering.js';

// Staleness means "the code moved since the grade was measured". The real
// signal is commitsSinceLastRun from the backend (git commits since the last
// scored run); the age fallback below only applies when that signal is
// unknowable (repo missing, no git, online project).
export const STALE_AFTER_DAYS = 7;

// Delta window: the "30d" column. Baseline is the newest run at or before
// the window start, so the delta reads "change over the last month" even
// when runs are unevenly spaced.
export const DELTA_WINDOW_DAYS = 30;

/** "7.2", "7.2/10", "7.2/10 Good" or 7.2 → number, else null. */
export function parseScore10(value) {
  if (value == null) return null;
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  const m = String(value).match(/^(\d+(?:\.\d+)?)/);
  return m ? parseFloat(m[1]) : null;
}

/** Case-insensitive identity for dimension/principle names across projects. */
export function nameKey(name) {
  return String(name || '').trim().toLowerCase();
}

/**
 * Restrict a compare-summary payload to the project's enabled standards,
 * exactly the way the Overview does it: same filter utils, so the scores,
 * severity totals and trend averages Compare shows for a project agree with
 * that project's own Overview. Pass the ids from
 * GET /projects/{id}/standards-visibility; a null/absent list means "no
 * filtering" (fail open — data is better than a blank row).
 */
export function applyVisibleStandards(summary, visibleIds) {
  if (!summary || !Array.isArray(visibleIds)) return summary;
  const visibleSet = new Set(visibleIds.map((id) => nameKey(id)));
  const dims = summary.dimensions || [];
  if (dims.every((d) => visibleSet.has(nameKey(d.dimension)))) return summary;
  const filteredTrend = filterTrendByVisibleStandards(summary.trend || [], visibleSet);
  const acc = filterAccumulatedByVisibleStandards(
    { dimensions: dims, summary: summary.summary || {} },
    visibleSet,
    filteredTrend,
    null,
  );
  return { ...summary, dimensions: acc.dimensions, summary: acc.summary, trend: filteredTrend };
}

export function daysBetween(isoA, isoB) {
  const a = new Date(isoA).getTime();
  const b = new Date(isoB).getTime();
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
  return (b - a) / 86400000;
}

export function sortedByDate(trend) {
  return (trend || [])
    .filter((e) => e && e.dateISO && e.numericAverage != null)
    .slice()
    .sort((a, b) => new Date(a.dateISO) - new Date(b.dateISO));
}

/**
 * Score movement over the delta window plus the sparkline series.
 * `pick` extracts the numeric value from a trend entry (defaults to the
 * accumulated average; the dimension view passes a per-dimension picker).
 *
 * `delta` is the change within the window (null when every run predates it —
 * nothing moved in the last month). `lastDelta` is the change between the
 * two most recent runs regardless of age, for a muted fallback display.
 */
export function trendDelta(trend, now, pick = (e) => e.numericAverage) {
  const entries = sortedByDate(trend)
    .map((e) => ({ dateISO: e.dateISO, value: pick(e) }))
    .filter((e) => e.value != null);
  const spark = entries.map((e) => e.value);
  if (entries.length < 2) return { delta: null, lastDelta: null, spark };
  const latest = entries[entries.length - 1];
  const previous = entries[entries.length - 2];
  const lastDelta = Math.round((latest.value - previous.value) * 10) / 10;
  const cutoff = new Date(now).getTime() - DELTA_WINDOW_DAYS * 86400000;
  let baseline = entries[0];
  for (const e of entries) {
    if (new Date(e.dateISO).getTime() <= cutoff) baseline = e;
    else break;
  }
  if (baseline === latest) return { delta: null, lastDelta, spark };
  return { delta: Math.round((latest.value - baseline.value) * 10) / 10, lastDelta, spark };
}

export function mean(values) {
  const xs = values.filter((v) => v != null);
  if (!xs.length) return null;
  return xs.reduce((a, b) => a + b, 0) / xs.length;
}

export const round1 = (x) => Math.round(x * 10) / 10;

export {
  buildRow, consequenceOf, consequenceLevel, sortRows, buildFleet,
} from './compareFleet.js';
export { buildDimensionsBoard, buildAttention } from './compareBoard.js';
export { buildDuelView } from './compareDuel.js';
export { buildDimensionAttention, buildDimensionView } from './compareDimensionView.js';
