import { useCallback } from 'react';
import { sharedKeys } from '../../../api/queryKeys.js';

export function buildPublishedAtMap(list) {
  const map = {};
  for (const p of list || []) {
    const id = p.id || p.name;
    if (id && p.publishedAt) map[id] = p.publishedAt;
  }
  return map;
}

// Upserts the just-published project into the shared list cache's `projects`
// array, merging over any existing entry with the same id (audit C3/C4).
// `local` is the LOCAL project object the publish() call was made with (see
// publishingLocalRef below) -- its originUrl/latestRunId/latestDoneRunId are
// copied over so the merge in projectsMerge.js immediately recognizes this as
// the SAME project (chips flip to PUBLISHED, no stale publish/update button)
// without waiting for the authoritative refresh to learn those fields from
// the backend. Falls back to whatever the existing entry already had for any
// field `local` doesn't know, so a merge never regresses already-good data.
export function upsertPublishedProject(projects, id, local) {
  const idx = projects.findIndex((p) => (p.id || p.name) === id);
  const existing = idx === -1 ? null : projects[idx];
  const merged = {
    ...existing,
    id,
    name: local?.name ?? existing?.name ?? id,
    publishedAt: Date.now(),
    publishedBy: null, // backend's published.json is authoritative; the UI
    // shows "published <relative time>" regardless (see PublishedMeta/
    // LocalPublishedMeta -- both render gracefully with no publishedBy).
    source: 'shared',
    latestRunId: local?.latestRunId ?? existing?.latestRunId ?? null,
    latestDoneRunId: local?.latestDoneRunId ?? existing?.latestDoneRunId ?? null,
    originUrl: local?.originUrl ?? existing?.originUrl ?? null,
  };
  if (idx === -1) return [...projects, merged];
  const next = [...projects];
  next[idx] = merged;
  return next;
}

// Synchronous, BEFORE any network round trip: patches the shared list
// cache with the just-published id the instant the job reports 'done', so
// every consumer of sharedKeys.list() (useMergedProjects' chips/action via
// useSharedProjects, and usePublishQueries' own publishedAtByProject) flips in
// the SAME render (audit C3/C4) instead of waiting up to 30s for the
// authoritative refresh below to land. Only uses `publishingLocalRef` when
// it actually corresponds to `id` -- a fresh mount that reconciles a job
// started elsewhere never had a local project object handed to it, and a
// stale ref must never get attributed to the wrong id.
export function useApplyOptimisticPublish({ queryClient, publishingLocalRef }) {
  return useCallback((id) => {
    const local = publishingLocalRef.current;
    const matchedLocal = local && (local.id ?? local.name) === id ? local : null;
    queryClient.setQueryData(sharedKeys.list(), (old) => ({
      ...old,
      projects: upsertPublishedProject(old?.projects ?? [], id, matchedLocal),
    }));
  }, [queryClient]);
}
