/**
 * Cross-project dimension board + attention-list builders for the Compare
 * tab's fleet view. Split out of compareModel.js — see compareModel.js for
 * the module-level docs.
 */
import { nameKey, parseScore10, trendDelta, mean } from './compareModel.js';
import { consequenceOf, consequenceLevel } from './compareFleet.js';

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
        ? Math.round(mean(entry.deltas) * 10) / 10
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
      if (worst) reasons.push({ type: 'worstDim', dim: worst.label, score: worst.score });
      if (row.delta != null && row.delta <= -0.3) reasons.push({ type: 'declining', delta: row.delta });
      if (row.stale) reasons.push({ type: 'stale', commits: row.commitsSince });
      if (row.coveragePct != null && row.coveragePct < 80) {
        reasons.push({ type: 'coverage', pct: row.coveragePct });
      }
      return { row, value, level: consequenceLevel(value), worstDim: worst?.key ?? null, reasons };
    })
    .sort((a, b) => b.value - a.value);
}
