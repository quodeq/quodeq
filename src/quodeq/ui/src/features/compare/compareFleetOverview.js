/**
 * The Compare landing's model: pure functions over the fleet rows and the
 * dimensions board, one per panel.
 *
 *   fleetKpis        the summary strip: score (and size-weighted), size,
 *                    violation density, critical density, freshness, spread
 *   sortFleet        the projects table's column sorts, best-first or reversed
 *   dimensionHealth  per dimension: grade mix, below-good count, weakest project
 *
 * Exposure is normalised by size throughout (exposureOf): raw counts favour
 * small projects.
 */
import { PERCENT } from '../../constants.js';
import { getGradeThresholds } from '../../utils/gradeThresholds.js';
import { exposureOf } from './compareDuelAnalysis.js';

export const FLEET_SORT = Object.freeze({
  SCORE: 'score', MOVE: 'move', FILES: 'files', DENSITY: 'density', CRITICAL: 'critical', FRESH: 'fresh',
});

// The tier under every configured threshold (the thresholds table stops at Poor).
export const LOWEST_TIER_LABEL = 'Critical';
const PER_THOUSAND = 1000;

const sum = (rows, pick) => rows.reduce((s, r) => s + (pick(r) || 0), 0);

/** The summary strip. `rows` are the scored rows; `fleet` is buildFleet's aggregate. */
export function fleetKpis(rows, fleet) {
  const files = sum(rows, (r) => r.totalFiles);
  const analysed = sum(rows, (r) => r.analyzedFiles);
  const base = analysed || files;
  const critical = sum(rows, (r) => r.severity?.critical);
  return {
    score: fleet.score,
    // A 3,000-file project weighs more than a 30-file one.
    weighted: files ? sum(rows, (r) => r.score * (r.totalFiles || 0)) / files : null,
    delta: fleet.delta,
    projects: rows.length,
    files,
    coverage: files && analysed ? Math.round((analysed / files) * PERCENT) : null,
    density: base ? (sum(rows, (r) => r.totalViolations) / base) * PERCENT : null,
    critical,
    criticalPerK: base ? (critical / base) * PER_THOUSAND : null,
    fresh: rows.filter((r) => !r.stale).length,
    stale: rows.filter((r) => r.stale).length,
    spread: fleet.spread,
    lead: fleet.lead,
    trail: fleet.trail,
  };
}

// Each key's "best" value is the largest: low density and fewer criticals
// are negated, missing values sort last.
const SORT_VALUE = Object.freeze({
  [FLEET_SORT.SCORE]: (r) => r.score,
  [FLEET_SORT.MOVE]: (r) => r.delta ?? -Infinity,
  [FLEET_SORT.FILES]: (r) => r.totalFiles ?? -Infinity,
  [FLEET_SORT.DENSITY]: (r) => -(exposureOf(r).per100 ?? Infinity),
  [FLEET_SORT.CRITICAL]: (r) => -(exposureOf(r).criticalPerK ?? Infinity),
  [FLEET_SORT.FRESH]: (r) => (r.lastISO ? Date.parse(r.lastISO) : -Infinity),
});

/**
 * Rows sorted by a column: best first when `desc`, worst first otherwise.
 * Rows with no value for the column stay last either way; ties keep name
 * order so the table never shuffles.
 */
export function sortFleet(rows, key, desc = true) {
  const value = SORT_VALUE[key];
  const known = rows.filter((r) => Number.isFinite(value(r)));
  const unknown = rows.filter((r) => !Number.isFinite(value(r)));
  const best = known.sort((a, b) => value(b) - value(a) || a.name.localeCompare(b.name));
  return (desc ? best : best.reverse()).concat(unknown.sort((a, b) => a.name.localeCompare(b.name)));
}

/**
 * Dimension health, weakest first: fleet average, 30-day movement, how many
 * projects sit in each grade tier (best tier first, empty tiers dropped),
 * how many are below good, and the weakest project.
 */
export function dimensionHealth(board, tiers = getGradeThresholds()) {
  const desc = [...tiers].sort((x, y) => y[0] - x[0]);
  const good = desc[Math.min(1, desc.length - 1)][0];
  const tierOf = (v) => desc.find(([threshold]) => v >= threshold)?.[1] ?? LOWEST_TIER_LABEL;
  const order = desc.map(([, label]) => label).concat(LOWEST_TIER_LABEL);
  return board
    .map((b) => {
      const scored = b.perProject.filter((p) => p.score != null);
      const mix = order
        .map((label) => ({ label, count: scored.filter((p) => tierOf(p.score) === label).length }))
        .filter((m) => m.count);
      return {
        key: b.key,
        label: b.label,
        avg: b.avg,
        delta: b.delta,
        violations: b.violations,
        total: scored.length,
        below: scored.filter((p) => p.score < good).length,
        mix,
        weakest: scored.reduce((w, p) => (!w || p.score < w.score ? p : w), null),
      };
    })
    .sort((x, y) => x.avg - y.avg);
}
