import { runCounts } from '../../dashboard/headlineStats.js';

/**
 * Per-row run-over-run deltas of majors and open types, newest first: each
 * row against the next row that has that count, so a row without counts (an
 * in-progress stub, an old run) never nulls out its neighbours' deltas.
 * @returns {Array<{majors: number|null, openTypes: number|null}>} aligned with `rows`
 */
export function computeCountDeltas(rows) {
  const deltas = rows.map(() => ({ majors: null, openTypes: null }));
  let nextMajors = null;
  let nextTypes = null;
  for (let i = rows.length - 1; i >= 0; i--) {
    const { majors, openTypes } = runCounts(rows[i]);
    if (majors !== null) {
      if (nextMajors !== null) deltas[i].majors = majors - nextMajors;
      nextMajors = majors;
    }
    if (openTypes !== null) {
      if (nextTypes !== null) deltas[i].openTypes = openTypes - nextTypes;
      nextTypes = openTypes;
    }
  }
  return deltas;
}
