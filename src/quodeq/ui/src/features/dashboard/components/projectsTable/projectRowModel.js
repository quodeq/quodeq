import { PROJECT_ACTION } from '../../dashboardVocab.js';
import { PROJECT_LOCATION } from '../../../../models/project.js';
import { PROJECT_SOURCE } from '../../../../vocab/projectSource.js';
import { projectIdOrSelf } from '../../../../utils/projectIdentity.js';

/** What a row's sync cell says about the project's copy on the server. */
export const SYNC_STATE = Object.freeze({ PUBLISHED: 'published', BEHIND: 'behind', NONE: 'none' });

/** The relocate action a row with a missing folder shows (the rest are PROJECT_ACTION). */
export const ROW_RELOCATE = 'relocate';

// The merged entry's `chips` value for a project on both sides (see projectsMerge.js).
const SIDES_BOTH = 'both';

/** Where a row's project lives, for the location cell. */
export const ROW_LOCATION = Object.freeze({ LOCAL: 'local', REMOTE: 'remote', MISSING: 'missing' });

// A local project whose folder is gone: the row offers relocate before anything else.
export function isPathMissing(project) {
  return project?.location === PROJECT_LOCATION.LOCAL && project.pathExists === false;
}

export function rowLocation(entry) {
  if (!entry.local) return ROW_LOCATION.REMOTE;
  return isPathMissing(entry.local) ? ROW_LOCATION.MISSING : ROW_LOCATION.LOCAL;
}

/**
 * The sync cell, read off the merged entry (see useMergedProjects): a
 * project on both sides whose action is `update` has a newer local run than
 * the published one, so the server copy is behind. `publishedAt` falls back
 * to the shared side for origin-URL matches (local objects only carry it for
 * id matches, see usePublish's publishedAtByProject).
 */
export function rowSync(entry) {
  const publishedAt = entry.local?.publishedAt ?? entry.shared?.publishedAt ?? null;
  if (!entry.shared) return { state: SYNC_STATE.NONE, publishedAt: null };
  if (entry.chips === SIDES_BOTH && entry.action === PROJECT_ACTION.UPDATE) return { state: SYNC_STATE.BEHIND, publishedAt };
  return { state: SYNC_STATE.PUBLISHED, publishedAt };
}

/**
 * The one action a row shows, the one its state calls for: relocate a
 * missing folder, else publish/update/pull from the merged entry. Every
 * rarer action lives in the row's ⋯ menu.
 */
export function rowAction(entry) {
  if (entry.local && isPathMissing(entry.local)) return ROW_RELOCATE;
  if (!entry.local && entry.shared) return PROJECT_ACTION.PULL;
  return entry.action === PROJECT_ACTION.PUBLISH || entry.action === PROJECT_ACTION.UPDATE ? entry.action : null;
}

/** The source a row's selection reports, matching the old card click. */
export function rowSource(entry) {
  return entry.local ? undefined : PROJECT_SOURCE.SHARED;
}

// A subproject has no merged entry of its own in the visible list: its
// entry comes from the unfiltered lookup, else a bare local-only stand-in.
export function childEntry(child, entryLookup) {
  const id = projectIdOrSelf(child);
  return entryLookup?.get(id) ?? { key: id, local: child, shared: null, chips: PROJECT_SOURCE.LOCAL, action: null };
}
