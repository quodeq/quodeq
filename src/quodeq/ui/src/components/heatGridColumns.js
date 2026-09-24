// Column ids both heat grids (HeatGridView, DimensionHeatGridView) sort and
// build headers by, and the header alignment value each uses for its one
// left-aligned column (name). Severity columns are covered by vocab/severity.js.
//
// Plain data, not re-exported through HeatGridCells.jsx's own module: that
// file is .jsx, and dimensionHeatGridModel.js (imported by
// dimensionHeatGridModel.test.js, which runs under Node's native test
// runner with no JSX loader) needs these without pulling in JSX.
export const COL_NAME = 'name';
export const COL_VIOLATIONS = 'violations';
export const COL_HEALTH = 'health';
export const COL_ALIGN_LEFT = 'left';
