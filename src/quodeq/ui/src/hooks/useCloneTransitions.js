import { useEffect, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useApi } from '../api/ApiContext.jsx';
import { projectsKeys } from '../api/queryKeys.js';
import { isCloneActive, CLONE_CODE_PROJECT_EXISTS } from '../api/projectClone.js';
import { SYNC_PHASE } from '../vocab/syncPhase.js';
import { invalidateProjects } from './invalidateProjects.js';

const ACTIVE_MS = 1000;
const IDLE_MS = 30000;

/**
 * A slot that ended with a project to show: DONE with the new project, or
 * the server's PROJECT_EXISTS refusal, whose `detail` is the id of the
 * project already registered for that url (the route answers 202 before
 * the duplicate check, so this is where "you already have it" lands).
 * @param {Object|undefined} slot
 * @returns {string|null} the project id, or null when the slot landed nothing
 */
export function landedProjectId(slot) {
  if (!slot) return null;
  if (slot.phase === SYNC_PHASE.DONE) return slot.projectId ?? null;
  if (slot.phase === SYNC_PHASE.ERROR && slot.code === CLONE_CODE_PROJECT_EXISTS) return slot.detail || null;
  return null;
}

// `tick` changes on every poll that lands, even when structural sharing hands back the same data object.
function useCloneDoneEdge(slot, tick, queryClient, onLanded) {
  const prev = useRef(null);
  const landed = useRef(onLanded);
  landed.current = onLanded;
  useEffect(() => {
    if (!slot) return;
    const was = prev.current;
    prev.current = slot;
    const projectId = landedProjectId(slot);
    if (projectId === null && slot.phase !== SYNC_PHASE.DONE) return;
    // A second clone can start and finish between two polls (DONE -> DONE): a new finishedAt is an edge too.
    if (was?.phase === slot.phase && was.finishedAt === slot.finishedAt) return;
    // The edge fires once per landing, on the poll that saw it, never on a
    // remount that reads a finished slot already in the cache.
    const fresh = was !== null;
    invalidateProjects(queryClient);
    if (fresh && projectId) landed.current?.({ ...slot, projectId });
  }, [slot, tick, queryClient]);
}

/**
 * The one poll of GET /api/projects/clone-status. Fast while a clone runs,
 * slow otherwise, and it re-lists the projects on each DONE edge, then calls
 * `onLanded(slot)` so the app can select the project that arrived. Mount it
 * exactly once (the app shell does); `useCloneStatus` is the passive reader.
 * A rejected status never throws: the slot stays unknown and not active.
 * @param {{ activeMs?: number, idleMs?: number, onLanded?: (slot: Object) => void }} [options]
 */
export function useCloneTransitions({ activeMs = ACTIVE_MS, idleMs = IDLE_MS, onLanded } = {}) {
  const { getCloneStatus } = useApi();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: projectsKeys.clone(),
    queryFn: getCloneStatus,
    refetchOnWindowFocus: false,
    refetchInterval: (q) => (isCloneActive(q.state.data) ? activeMs : idleMs),
  });
  useCloneDoneEdge(query.data, query.dataUpdatedAt, queryClient, onLanded);
}
