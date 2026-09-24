// Column ids both heat grids (HeatGridView, DimensionHeatGridView) sort and
// build headers by, and the header alignment value each uses for its one
// left-aligned column (name). Severity columns are covered by vocab/severity.js.
//
// Plain data in a .js leaf, imported directly by both grids and
// dimensionHeatGridModel.js (whose node --test suite has no JSX loader).
export const COL_NAME = 'name';
export const COL_VIOLATIONS = 'violations';
export const COL_HEALTH = 'health';
export const COL_ALIGN_LEFT = 'left';
