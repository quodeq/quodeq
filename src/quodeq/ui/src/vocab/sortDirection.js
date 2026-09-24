// Sort-direction toggle shared by every sortable table/grid: Compare's
// fleet matrix and projects table, the map heat grid, the violations heat
// grid. No Python mirror: a purely client-side UI concept.
export const SORT_DIR = Object.freeze({ ASC: 'asc', DESC: 'desc' });

/**
 * Column-header click handler shared by the map and violations heat grids
 * (HeatGridView.jsx, DimensionHeatGridView.jsx): clicking the active column
 * flips its direction; clicking a different column selects it, defaulting to
 * ascending only for `ascCol` (the name column in both grids).
 */
export function makeColumnSortHandler({ sortCol, setSortCol, setSortDir, ascCol }) {
  return (col) => {
    if (sortCol === col) {
      setSortDir((d) => (d === SORT_DIR.ASC ? SORT_DIR.DESC : SORT_DIR.ASC));
    } else {
      setSortCol(col);
      setSortDir(col === ascCol ? SORT_DIR.ASC : SORT_DIR.DESC);
    }
  };
}
