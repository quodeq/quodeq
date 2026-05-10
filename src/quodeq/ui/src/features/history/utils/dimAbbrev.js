/**
 * Shorter labels for dim summaries so the row's dimensions cell can fit
 * the count and names instead of truncating after the first dim. Used
 * by both the terminal `formatDimSummary` (HistoryPage.jsx) and the
 * live `formatLiveDimSummary` so the truncation rules stay consistent.
 */
export const DIM_ABBREV = {
  flexibility: 'flex',
  maintainability: 'maint',
  performance: 'perf',
  reliability: 'rel',
  security: 'sec',
  usability: 'usab',
};

export function abbrevDim(name) {
  if (!name) return name;
  const lower = String(name).toLowerCase();
  return DIM_ABBREV[lower] || (lower.length > 5 ? lower.slice(0, 4) : lower);
}
