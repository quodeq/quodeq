import { useMemo } from 'react';
import { mergeProjects, deriveAction } from '../projectsMerge.js';

const COMPARATORS = {
  activity: (a, b) => (b.lastActivity ?? 0) - (a.lastActivity ?? 0),
  name: (a, b) => (a.displayName || a.name || '').localeCompare(b.displayName || b.name || ''),
  score: (a, b) => (b.score ?? -1) - (a.score ?? -1),
};

export function useMergedProjects({ localProjects = [], sharedProjects = [], configured = false, filters } = {}) {
  const { query = '', location = 'all', sort = 'activity' } = filters || {};
  return useMemo(() => {
    let entries = mergeProjects(localProjects, sharedProjects);
    if (query) {
      const q = query.toLowerCase();
      entries = entries.filter(
        (e) => (e.displayName || '').toLowerCase().includes(q) || (e.name || '').toLowerCase().includes(q),
      );
    }
    if (location === 'local') entries = entries.filter((e) => e.local);
    else if (location === 'shared') entries = entries.filter((e) => e.shared);
    entries.sort(COMPARATORS[sort] || COMPARATORS.activity);
    return entries.map((e) => ({ ...e, action: deriveAction(e, { configured }) }));
  }, [localProjects, sharedProjects, configured, query, location, sort]);
}
