/**
 * Pure row/column math for CompareMatrix — sort ordering and per-column
 * extremes (for the min/max border treatment). Split out so the component
 * only owns rendering.
 */
export const OVERALL = '__overall';

function valueOf(row, key) {
  return key === OVERALL ? row.overall : row.cells[key]?.score;
}

/**
 * Per-column {min, max} for the border treatment. A column where every
 * project holds the same score has no spread to point at, so it's omitted.
 */
export function computeMatrixExtremes(columns, matrixRows) {
  const extremes = new Map();
  for (const col of columns) {
    let min = Infinity;
    let max = -Infinity;
    for (const row of matrixRows) {
      const s = row.cells[col.key]?.score;
      if (s == null) continue;
      if (s < min) min = s;
      if (s > max) max = s;
    }
    if (min !== Infinity && min !== max) extremes.set(col.key, { min, max });
  }
  return extremes;
}

/**
 * `sort` orders by column value (desc/asc); unscored rows always sink to
 * the bottom regardless of direction. `sort: null` keeps the caller's order.
 */
export function sortMatrixRows(matrixRows, sort) {
  if (!sort) return matrixRows;
  const dir = sort.dir === 'asc' ? 1 : -1;
  return matrixRows.slice().sort((a, b) => {
    const av = valueOf(a, sort.key);
    const bv = valueOf(b, sort.key);
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    return (av - bv) * dir;
  });
}
