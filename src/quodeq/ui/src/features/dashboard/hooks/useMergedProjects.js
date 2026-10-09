import { useMemo } from 'react';
import { mergeProjects, deriveAction } from '../projectsMerge.js';
import { PROJECT_SOURCE } from '../../../vocab/projectSource.js';
import { naturalDirection } from '../projectsSort.js';

// Each comparator sorts in its column's natural direction (see
// projectsSort.js); a reversed `dir` negates it. Missing values sink to the
// bottom either way.
const COMPARATORS = {
  activity: (a, b) => (b.lastActivity ?? 0) - (a.lastActivity ?? 0),
  name: (a, b) => (a.displayName || a.name || '').localeCompare(b.displayName || b.name || ''),
  score: (a, b) => (b.score ?? -1) - (a.score ?? -1),
  files: (a, b) => (filesOf(b) ?? -1) - (filesOf(a) ?? -1),
};

function filesOf(e) {
  return e.local?.filesCount ?? e.shared?.filesCount ?? null;
}

function comparatorFor(sort, dir) {
  const key = COMPARATORS[sort] ? sort : 'activity';
  const base = COMPARATORS[key];
  return dir && dir !== naturalDirection(key) ? (a, b) => base(b, a) : base;
}

/**
 * useMergedProjects -- merges local + shared project lists into the one
 * flat list the Projects page renders (no tabs -- see ProjectsPage.jsx).
 *
 * Delegates the actual merge/dedup to `mergeProjects` (projectsMerge.js),
 * then layers in query/location filtering, sorting, and a per-entry
 * `action` (publish/update/pull) via `deriveAction`. Called at multiple call
 * sites with different filter subsets -- e.g. the unfiltered call feeding
 * ProjectsPage's `isEmpty`/`allEntries` vs. the location-filtered call
 * feeding the visible list -- so filters stay optional and independently
 * omittable.
 */
export function useMergedProjects({ localProjects = [], sharedProjects = [], configured = false, filters } = {}) {
  const { query = '', location = 'all', sort = 'activity', dir } = filters || {};
  return useMemo(() => {
    let entries = mergeProjects(localProjects, sharedProjects);
    if (query) {
      const q = query.toLowerCase();
      entries = entries.filter(
        (e) => (e.displayName || '').toLowerCase().includes(q) || (e.name || '').toLowerCase().includes(q),
      );
    }
    if (location === PROJECT_SOURCE.LOCAL) entries = entries.filter((e) => e.local);
    else if (location === PROJECT_SOURCE.SHARED) entries = entries.filter((e) => e.shared);
    entries.sort(comparatorFor(sort, dir));
    return entries.map((e) => ({ ...e, action: deriveAction(e, { configured }) }));
  }, [localProjects, sharedProjects, configured, query, location, sort, dir]);
}
