/**
 * Cross-project dimension board + attention-list builders for the Compare
 * tab's fleet view. Split out of compareModel.js — see compareModel.js for
 * the module-level docs.
 */
import { nameKey, parseScore10, trendDelta, mean } from './compareModel.js';
import { consequenceOf, consequenceLevel } from './compareFleet.js';
import { roundOneDecimal } from '../../utils/rounding.js';

// Score drop over the delta window (0-10 scale) that earns a row the
// "declining" reason. Deliberately not trendUtils.DECLINING_THRESHOLD:
// that one drives the TrendBadge arrow on its own scale and is not
// interchangeable with this cutoff.
const DECLINING_DELTA = -0.3;
// Analyzed-files share (percent) below which a row gets the coverage-gap
// reason.
const COVERAGE_GAP_PCT = 80;

// buildAttention's machine-readable reason kinds; CompareFleetView turns
// each into its own copy line.
export const REASON_TYPE = Object.freeze({
  WORST_DIM: 'worstDim', DECLINING: 'declining', STALE: 'stale', COVERAGE: 'coverage',
});

/** Union of dimensions across scope, each with fleet stats + per-project scores. */
export function buildDimensionsBoard(rows, now, summariesById) {
  const byKey = new Map();
  for (const row of rows) {
    for (const dim of row.dims) {
      let entry = byKey.get(dim.key);
      if (!entry) {
        entry = { key: dim.key, label: dim.label, perProject: [], violations: 0, deltas: [] };
        byKey.set(dim.key, entry);
      }
      entry.perProject.push({ id: row.id, name: row.name, score: dim.score, row, dim });
      entry.violations += dim.violations;
      const summary = summariesById?.[row.id];
      if (summary) {
        const { delta } = trendDelta(summary.trend, now, (e) => {
          const detail = (e.dimensionDetails || []).find((d) => nameKey(d.dimension) === dim.key);
          return detail ? parseScore10(detail.score) : null;
        });
        if (delta != null) entry.deltas.push(delta);
      }
    }
  }
  return Array.from(byKey.values())
    .map((entry) => ({
      key: entry.key,
      label: entry.label,
      avg: mean(entry.perProject.map((p) => p.score)),
      delta: entry.deltas.length
        ? roundOneDecimal(mean(entry.deltas))
        : null,
      violations: entry.violations,
      perProject: entry.perProject
        .filter((p) => p.score != null)
        .sort((a, b) => b.score - a.score),
    }))
    .sort((a, b) => a.label.localeCompare(b.label));
}

/**
 * Every scored row ranked by consequence, with machine-readable reasons the
 * component turns into copy (worst-dimension, declining, stale,
 * coverage-gap). The VIEW caps the strip at 3 and offers the rest behind an
 * expand toggle, so the cap lives there, not here.
 */
export function buildAttention(rows) {
  return rows
    .filter((r) => r.hasData)
    .map((row) => {
      const value = consequenceOf(row);
      const worst = row.dims
        .filter((d) => d.score != null)
        .reduce((acc, d) => (acc == null || d.score < acc.score ? d : acc), null);
      const reasons = [];
      if (worst) reasons.push({ type: REASON_TYPE.WORST_DIM, dim: worst.label, score: worst.score });
      if (row.delta != null && row.delta <= DECLINING_DELTA) reasons.push({ type: REASON_TYPE.DECLINING, delta: row.delta });
      if (row.stale) reasons.push({ type: REASON_TYPE.STALE, commits: row.commitsSince });
      if (row.coveragePct != null && row.coveragePct < COVERAGE_GAP_PCT) {
        reasons.push({ type: REASON_TYPE.COVERAGE, pct: row.coveragePct });
      }
      return { row, value, level: consequenceLevel(value), worstDim: worst?.key ?? null, reasons };
    })
    .sort((a, b) => b.value - a.value);
}
