import { useMemo } from 'react';
import { useSharedProjects } from './useSharedProjects.js';
import { usePublish } from './usePublish.js';
import { useMergedProjects } from './useMergedProjects.js';

export function computeProjectTree(projects) {
  const lookup = {};
  for (const p of projects) {
    const id = p.id || p.name || p;
    const name = p.name || p;
    lookup[id] = p;
    lookup[name] = p;
  }
  const children = {};
  const roots = [];
  for (const p of projects) {
    const parent = p.parent;
    if (parent && lookup[parent]) {
      const parentId = lookup[parent].id || lookup[parent].name || parent;
      if (!children[parentId]) children[parentId] = [];
      children[parentId].push(p);
    } else {
      roots.push(p);
    }
  }
  return { children, roots };
}

// Local project objects never carry publishedAt on their own (it lives
// only on the shared list's git-log-derived metadata) -- merge it in by
// id/name so ProjectCard can read `project.publishedAt` uniformly. Belt
// and suspenders with `entry.shared?.publishedAt` below (the merged
// entry already carries it too, since usePublish and useSharedProjects
// share the same sharedKeys.list() cache entry -- see Task 5) but this
// keeps LocalPublishedMeta's prop stable even for callers that only ever
// look at `project.publishedAt` directly.
function useProjectsWithPublished(projects, sharedConfigured, publishedAtByProject) {
  return useMemo(() => {
    if (!sharedConfigured || Object.keys(publishedAtByProject).length === 0) return projects;
    return projects.map((p) => {
      const id = p.id || p.name || p;
      const publishedAt = publishedAtByProject[id];
      return publishedAt ? { ...p, publishedAt } : p;
    });
  }, [projects, publishedAtByProject, sharedConfigured]);
}

// Subproject nesting: computed over the same flat local list the merge
// draws from, so a child project's own derived chips/action (looked up
// via `localEntryById`) stay in sync with its parent's.
function useProjectTree(projectsWithPublished) {
  const { children } = useMemo(() => computeProjectTree(projectsWithPublished), [projectsWithPublished]);
  const childIdSet = useMemo(() => {
    const set = new Set();
    for (const list of Object.values(children)) {
      for (const c of list) set.add(c.id || c.name || c);
    }
    return set;
  }, [children]);
  return { children, childIdSet };
}

// Built from the UNFILTERED merge (not the query-filtered `entries` below)
// so a subproject keeps its own chips/publish-or-update action even when
// the current query only matches its parent (or only matches a sibling) --
// otherwise a matching parent would render children with no chips/button
// at all the moment a query excluded the child's own entry.
// Chips are stripped here (and at the root-card site below) when no
// shared repo is configured: every card would read LOCAL, which
// distinguishes nothing.
function useLocalEntryById(allEntries, sharedConfigured) {
  return useMemo(() => {
    const map = new Map();
    for (const e of allEntries) {
      if (e.local) {
        map.set(
          e.local.id || e.local.name || e.local,
          sharedConfigured ? e : { ...e, chips: null },
        );
      }
    }
    return map;
  }, [allEntries, sharedConfigured]);
}

// Group-aware query filter: a name search must not hide a whole
// parent/child group just because only one side of it matched. A parent
// entry survives the query if its own name matches OR any of its
// children's does; children are always excluded from top-level rendering
// below regardless of their own match (see `visibleEntries`) since they
// render nested under their parent, so their individual match status
// doesn't otherwise matter here.
function useFilteredEntries(locationFilteredEntries, query, children) {
  return useMemo(() => {
    if (!query) return locationFilteredEntries;
    const matches = (displayName, name) =>
      (displayName || '').toLowerCase().includes(query) || (name || '').toLowerCase().includes(query);
    return locationFilteredEntries.filter((e) => {
      if (matches(e.displayName, e.name)) return true;
      if (!e.local) return false;
      const localId = e.local.id || e.local.name || e.local;
      const childList = children[localId];
      return !!childList && childList.some((c) => matches(c.displayName, c.name));
    });
  }, [locationFilteredEntries, query, children]);
}

// Cached-first shared sync (see useSharedProjects.js's own doc comment for
// the full contract) plus publish action + job-progress polling for local
// cards (Task 20). usePublish only fetches shared status/list (both with
// refresh:false, so this never forces a real git fetch) when there's
// actually something to decorate: at least one local card. Hooks run
// unconditionally either way; only the internal effect is gated.
function useSharedAndPublish(projects) {
  const shared = useSharedProjects();
  const {
    configured: sharedConfigured,
    publishedAtByProject,
    publishState,
    publishingProject,
    publishError,
    publishErrorProject,
    publish,
  } = usePublish({ enabled: projects.length > 0 });
  return { shared, sharedConfigured, publishedAtByProject, publishState, publishingProject, publishError, publishErrorProject, publish };
}

// The unfiltered merge (basis for the id->entry lookup and the "is there
// anything at all" check) and the location-filtered-but-not-query-filtered
// merge (query matching needs subproject-group awareness, folded in by
// useFilteredEntries above useMergedProjects has no notion of). With no
// shared repo configured the location filter is forced to 'all': the pill
// to change it is hidden then, and a leftover location=shared in the nav
// params would otherwise blank the page with no visible control to clear it.
function useEntryLists(projectsWithPublished, shared, filters) {
  const allEntries = useMergedProjects({
    localProjects: projectsWithPublished,
    sharedProjects: shared.projects,
    configured: shared.configured,
  });
  const locationFilteredEntries = useMergedProjects({
    localProjects: projectsWithPublished,
    sharedProjects: shared.projects,
    configured: shared.configured,
    filters: {
      location: shared.configured ? filters?.location : 'all',
      sort: filters?.sort,
    },
  });
  return { allEntries, locationFilteredEntries };
}

// The full merge/filter pipeline that backs ProjectsPage's render: shared
// project sync, publish state, the local/shared merge (unfiltered and
// location-filtered), subproject nesting, and the query filter. Extracted
// verbatim (same hooks, same deps, same order) from ProjectsPage's body.
export function useProjectsPageData({ projects, filters }) {
  const { shared, sharedConfigured, publishedAtByProject, publishState, publishingProject, publishError, publishErrorProject, publish } = useSharedAndPublish(projects);
  const projectsWithPublished = useProjectsWithPublished(projects, sharedConfigured, publishedAtByProject);
  const { allEntries, locationFilteredEntries } = useEntryLists(projectsWithPublished, shared, filters);
  const { children, childIdSet } = useProjectTree(projectsWithPublished);
  const localEntryById = useLocalEntryById(allEntries, shared.configured);

  const query = (filters?.query || '').trim().toLowerCase();
  const entries = useFilteredEntries(locationFilteredEntries, query, children);

  const publishActions = {
    publishState,
    publishingProject,
    publishError,
    publishErrorProject,
    // Passes the local project object alongside its id -- usePublish's own
    // done-branch optimistic cache patch (audit C3/C4) needs
    // originUrl/latestRunId/latestDoneRunId to attribute the completed
    // publish to the right merged entry, and CardFooter's onClick only ever
    // hands back the bare id/name string.
    onPublish: (id) => publish(id, localEntryById.get(id)?.local),
  };

  // Based on the UNFILTERED merge -- filtering everything out must never
  // show the "add your first project" CTA (there's no way to clear a filter
  // from there); that's the post-filter "no projects match" line below
  // instead. The CTA is only for a page with truly nothing on it at all.
  const isEmpty = allEntries.length === 0;
  // Child (subproject) entries render nested under their root via
  // ProjectCardGroup/ProjectChildren, not as their own top-level card.
  const visibleEntries = entries.filter(
    (e) => !(e.local && childIdSet.has(e.local.id || e.local.name || e.local)),
  );

  return { shared, children, localEntryById, publishActions, isEmpty, visibleEntries };
}
