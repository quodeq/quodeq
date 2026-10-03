import { useQuery } from '@tanstack/react-query';
import { useApi } from '../api/ApiContext.jsx';
import { projectsKeys } from '../api/queryKeys.js';
import { isCloneActive } from '../api/projectClone.js';
import { SYNC_PHASE } from '../vocab/syncPhase.js';

/**
 * The project clone job's slot as a passive observer: it never polls on its
 * own (`useCloneTransitions`, mounted once by the app shell, does) and only
 * reads what that poll put in the cache. A rejected status reads as "nothing
 * cloning".
 * @returns {{ slot: (Object|undefined), active: boolean, failed: boolean, done: boolean }}
 */
export function useCloneStatus() {
  const { getCloneStatus } = useApi();
  const { data: slot } = useQuery({
    queryKey: projectsKeys.clone(),
    queryFn: getCloneStatus,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
  return {
    slot,
    active: isCloneActive(slot),
    failed: slot?.phase === SYNC_PHASE.ERROR,
    done: slot?.phase === SYNC_PHASE.DONE,
  };
}
