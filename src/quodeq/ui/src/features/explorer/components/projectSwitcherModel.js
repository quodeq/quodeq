/**
 * Pure model for the topbar project switcher: turns the local and remote
 * projects lists into the rows the popover shows (most recently evaluated
 * first, subprojects labelled "parent / child", remote ones tagged) and
 * filters them by the search query.
 */
import { gradeLabel } from '../../../utils/formatters.js';
import { projectIdOrSelf } from '../../../utils/projectIdentity.js';
import { mergeProjects } from '../../dashboard/projectsMerge.js';
import { PROJECT_SOURCE } from '../../../vocab/projectSource.js';

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

/** The remote projects with no local copy, matched the way Repositories
 * pairs them (same id, else same origin URL); a pulled one opens locally. */
function remoteOnly(locals, sharedProjects) {
  if (!Array.isArray(sharedProjects) || sharedProjects.length === 0) return [];
  return mergeProjects(locals, sharedProjects).filter((e) => !e.local).map((e) => e.shared);
}

/**
 * @param {Array<object|string>} projects - the local projects list
 * @param {Array<object>} [sharedProjects] - the remote projects list
 * @returns {Array<{id: string, label: string, search: string, grade: string|null, source: string, project: object}>}
 */
export function buildSwitcherRows(projects, sharedProjects) {
  const locals = (Array.isArray(projects) ? projects : []).map((p) => (typeof p === 'string' ? { name: p } : p));
  const remotes = new Set(remoteOnly(locals, sharedProjects));
  const objects = [...locals, ...remotes];
  // A subproject's `parent` names its root by id or name (see computeProjectTree).
  const byKey = new Map();
  for (const p of objects) {
    byKey.set(projectIdOrSelf(p), p);
    // First wins, so a remote project sharing a local one's name never takes its children.
    if (p.name && !byKey.has(p.name)) byKey.set(p.name, p);
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
      source: remotes.has(p) ? PROJECT_SOURCE.SHARED : PROJECT_SOURCE.LOCAL,
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
