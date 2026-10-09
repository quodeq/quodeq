/**
 * Opening one project's dimension from the fleet screen: the project's own
 * dimension page at the run that scored it, or the project itself when that
 * page is not reachable (a remote project, or no run id). The score matrix's
 * cells and the attention list's "open <dimension>" link both go through it.
 */
export function openProjectDimension(row, dim, onOpenProject, onOpenProjectDimension) {
  if (!dim || row.remote || !dim.fromRunId || !onOpenProjectDimension) return onOpenProject(row.id);
  return onOpenProjectDimension({ id: row.id, source: row.source, runId: dim.fromRunId, dimName: dim.name, dateLabel: dim.fromDateLabel });
}
