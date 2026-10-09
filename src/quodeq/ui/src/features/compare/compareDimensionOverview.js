/**
 * The dimension drill-down's model, one level below the fleet overview:
 * the same table, heatmap and grade-mix pieces, fed with one dimension's
 * numbers. Pure functions over buildDimensionView's model.
 *
 *   dimensionRows       standings reshaped as fleet rows: the score is the
 *                       dimension score, the "dims" are its principles, the
 *                       violations and severity are this dimension's
 *   dimensionKpis       the summary strip
 *   principleHealth     per principle: grade mix, below good, coverage,
 *                       leader and trailer, weakest first
 */
import { PERCENT } from '../../constants.js';
import { dimensionHealth } from './compareFleetOverview.js';
import { goodThreshold } from './compareDuelAnalysis.js';

const PER_THOUSAND = 1000;

/**
 * Each standing as a fleet row. Principle cells carry their own nav target
 * (the principle page of that project), which the heatmap opens.
 */
export function dimensionRows(view) {
  const cellsByKey = new Map(view.principles.map((p) => [p.key, new Map(p.perProject.map((x) => [x.id, x]))]));
  return view.standings.map((s) => ({
    ...s.row,
    score: s.score,
    delta: s.delta,
    lastDelta: s.lastDelta,
    totalViolations: s.violations,
    totalCompliance: s.compliance,
    severity: s.severity,
    dims: s.principles
      .filter((p) => p.score != null)
      .map((p) => ({ key: p.key, label: p.label, name: p.name, score: p.score, cell: cellsByKey.get(p.key)?.get(s.row.id) ?? null })),
  }));
}

/** The summary strip. `scopeCount` is how many projects are in scope at all. */
export function dimensionKpis(view, rows, scopeCount, good = goodThreshold()) {
  const base = rows.reduce((sum, r) => sum + (r.analyzedFiles || r.totalFiles || 0), 0);
  const violations = rows.reduce((sum, r) => sum + r.totalViolations, 0);
  const critical = rows.reduce((sum, r) => sum + (r.severity?.critical ?? 0), 0);
  return {
    score: view.avg,
    delta: view.delta,
    projects: rows.length,
    below: rows.filter((r) => r.score < good).length,
    scope: Math.max(scopeCount, rows.length),
    density: base ? (violations / base) * PERCENT : null,
    critical,
    criticalPerK: base ? (critical / base) * PER_THOUSAND : null,
    spread: view.spread,
    lead: view.lead,
    trail: view.trail,
  };
}

/**
 * Principle health, weakest first: dimensionHealth's grade mix and
 * below-good count, plus coverage (how many of the dimension's projects
 * scored the principle: an average over 2 of 9 is thin) and the leader.
 */
export function principleHealth(view, tiers) {
  const asBoard = view.principles.map((p) => ({ key: p.key, label: p.label, avg: p.avg, delta: null, violations: 0, perProject: p.perProject }));
  const byKey = new Map(view.principles.map((p) => [p.key, p]));
  return dimensionHealth(asBoard, tiers).map((h) => ({
    ...h,
    of: view.standings.length,
    lead: byKey.get(h.key)?.lead ?? null,
    trail: h.weakest,
  }));
}
