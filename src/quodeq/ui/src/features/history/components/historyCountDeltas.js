/**
 * Per-row run-over-run deltas of majors and open types, newest first.
 *
 * Runs refresh different dimension sets (a cancelled run scored two, a
 * scoped run one), so a delta over each row's grand total would swing with
 * the set, not the code. Each scored row compares with the next scored row
 * over the dimensions they share; a row with no score (a partial) takes no
 * part, and rows sharing no dimension get no delta.
 * @returns {Array<{majors: number|null, openTypes: number|null}>} aligned with `rows`
 */

function countsByDimension(row) {
  const map = new Map();
  for (const d of row?.dimensionDetails || []) {
    if (d?.dimension && typeof d.majors === 'number' && typeof d.openTypes === 'number') {
      map.set(String(d.dimension).toLowerCase(), { majors: d.majors, openTypes: d.openTypes });
    }
  }
  return map;
}

function isScored(row) {
  return !Number.isNaN(parseFloat(row?.numericAverage));
}

function sharedDelta(current, next, field) {
  let shared = 0;
  let total = 0;
  for (const [dim, counts] of current) {
    const before = next.get(dim);
    if (!before) continue;
    shared += 1;
    total += counts[field] - before[field];
  }
  return shared > 0 ? total : null;
}

export function computeCountDeltas(rows) {
  const deltas = rows.map(() => ({ majors: null, openTypes: null }));
  let next = null;
  for (let i = rows.length - 1; i >= 0; i--) {
    if (!isScored(rows[i])) continue;
    const current = countsByDimension(rows[i]);
    if (current.size === 0) continue;
    if (next) deltas[i] = { majors: sharedDelta(current, next, 'majors'), openTypes: sharedDelta(current, next, 'openTypes') };
    next = current;
  }
  return deltas;
}
