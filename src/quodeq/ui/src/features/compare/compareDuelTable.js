/**
 * The duel score table's model: one shared, zoomed 0-10 axis with the grade
 * zones on it, row sorting, and the one-line tally a manager reads first.
 * Pure; CompareDuelTable renders it.
 */
import { PERCENT, SCORE_SCALE_MAX } from '../../constants.js';
import { getGradeThresholds } from '../../utils/gradeThresholds.js';
import { EVEN_BAND } from './compareDuelAnalysis.js';

export const TABLE_SORT = Object.freeze({ GAP: 'gap', A: 'a', B: 'b', NAME: 'name' });

// The axis starts this far below the lowest score and ends this far above
// the highest, each on a whole point.
const AXIS_MARGIN = 0.5;
// Axes spanning more than this many points tick every other point.
const DENSE_SPAN = 6;

const scoreOf = (side) => (row) => (row[side] == null ? -1 : row[side]);
const gapSize = (row) => (row.gap == null ? -1 : Math.abs(row.gap));

const COMPARE = Object.freeze({
  [TABLE_SORT.GAP]: (x, y) => gapSize(y) - gapSize(x),
  [TABLE_SORT.A]: (x, y) => scoreOf('a')(y) - scoreOf('a')(x),
  [TABLE_SORT.B]: (x, y) => scoreOf('b')(y) - scoreOf('b')(x),
  [TABLE_SORT.NAME]: (x, y) => x.label.localeCompare(y.label),
});

/** A sorted copy; ties keep name order so the table never shuffles. */
export function sortScoreRows(rows, key) {
  const byName = COMPARE[TABLE_SORT.NAME];
  return [...rows].sort((x, y) => COMPARE[key](x, y) || byName(x, y));
}

/**
 * A score axis fitted to `values`: from just under the lowest to just over
 * the highest (whole points, within 0-10), integer ticks, and the grade zones that fall inside it (ascending,
 * each {from, to, label}). `at(v)` is the 0-100 position. Shared by the
 * duel's score table and the fleet's projects table.
 */
export function scoreAxisFor(scores, tiers = getGradeThresholds()) {
  const values = scores.filter((v) => v != null);
  const lo = values.length ? Math.max(0, Math.floor(Math.min(...values) - AXIS_MARGIN)) : 0;
  const hi = values.length ? Math.min(SCORE_SCALE_MAX, Math.ceil(Math.max(...values) + AXIS_MARGIN)) : SCORE_SCALE_MAX;
  const step = hi - lo > DENSE_SPAN ? 2 : 1;
  const ticks = [];
  for (let v = lo; v <= hi; v += step) ticks.push(v);
  const ascending = [...tiers].sort((x, y) => x[0] - y[0]);
  const zones = ascending
    .map(([from, label], i) => ({ from: Math.max(from, lo), to: ascending[i + 1]?.[0] ?? hi, label }))
    .filter((z) => z.to > lo && z.to > z.from);
  return { lo, hi, ticks, zones, at: (v) => ((v - lo) / (hi - lo || 1)) * PERCENT };
}

/** The duel score table's axis: every dimension and principle score of both sides. */
export function scoreAxis(duel, tiers = getGradeThresholds()) {
  const values = duel.dimensions.flatMap((d) => [d.a, d.b])
    .concat(duel.principles.flatMap((g) => g.items.flatMap((p) => [p.a, p.b])));
  return scoreAxisFor(values, tiers);
}

/**
 * Who leads on how many shared dimensions (a gap under EVEN_BAND is even),
 * and the single widest gap either way.
 */
export function dimensionTally(duel) {
  const shared = duel.dimensions.filter((d) => d.shared);
  const widest = shared.reduce((w, d) => (!w || Math.abs(d.gap) > Math.abs(w.gap) ? d : w), null);
  return {
    total: shared.length,
    a: shared.filter((d) => d.gap >= EVEN_BAND).length,
    b: shared.filter((d) => d.gap <= -EVEN_BAND).length,
    even: shared.filter((d) => Math.abs(d.gap) < EVEN_BAND).length,
    widest,
  };
}
