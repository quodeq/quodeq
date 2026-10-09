/**
 * Pure model for the topbar project switcher: turns the local projects list
 * into the rows the popover shows (most recently evaluated first, subprojects
 * labelled "parent / child") and filters them by the search query.
 */
import { gradeLabel } from '../../../utils/formatters.js';
import { projectIdOrSelf } from '../../../utils/projectIdentity.js';

function displayNameOf(p) {
  return p.displayName || p.name || projectIdOrSelf(p);
}

// ISO dates sort as strings; a project never evaluated sinks to the bottom.
function byLatestDateDesc(a, b) {
  const da = a.latestDate || '';
  const db = b.latestDate || '';
  if (da === db) return 0;
  return da < db ? 1 : -1;
}

/**
 * @param {Array<object|string>} projects - the local projects list
 * @returns {Array<{id: string, label: string, search: string, grade: string|null, project: object}>}
 */
export function buildSwitcherRows(projects) {
  if (!Array.isArray(projects)) return [];
  const objects = projects.map((p) => (typeof p === 'string' ? { name: p } : p));
  // A subproject's `parent` names its root by id or name (see computeProjectTree).
  const byKey = new Map();
  for (const p of objects) {
    byKey.set(projectIdOrSelf(p), p);
    if (p.name) byKey.set(p.name, p);
  }
  return [...objects].sort(byLatestDateDesc).map((p) => {
    const parent = p.parent ? byKey.get(p.parent) : null;
    const own = displayNameOf(p);
    const label = parent ? `${displayNameOf(parent)} / ${own}` : own;
    return {
      id: projectIdOrSelf(p),
      label,
      search: `${label} ${p.name || ''}`.toLowerCase(),
      grade: gradeLabel(p.overallGrade ?? p.latestGrade),
      project: p,
    };
  });
}

/** Rows whose name or display name contains the query (case-insensitive). */
export function filterSwitcherRows(rows, query) {
  const q = (query || '').trim().toLowerCase();
  if (!q) return rows;
  return rows.filter((r) => r.search.includes(q));
}
