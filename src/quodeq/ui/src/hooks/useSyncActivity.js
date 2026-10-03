import { useQuery } from '@tanstack/react-query';
import { useApi } from '../api/ApiContext.jsx';
import { sharedKeys } from '../api/queryKeys.js';
import { anyActive } from '../api/syncStatus.js';
import { useCloneStatus } from './useCloneStatus.js';

/**
 * Whether a team-results job (connect, refresh or pull) or a project clone is
 * running right now.
 *
 * A passive observer of the shared status and clone slot queries: it never
 * polls on its own (the screen that shows the sync, `useSyncStatus`, and the
 * app shell's `useCloneTransitions` do) and only reads what those polls put in
 * the cache, so the top bar can sweep its loading hairline while the strip
 * says "downloading" or "reading projects", or while a clone downloads.
 */
export function useSyncActivity() {
  const { getSyncStatus } = useApi();
  const clone = useCloneStatus();
  const { data } = useQuery({
    queryKey: sharedKeys.status(),
    queryFn: getSyncStatus,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    select: anyActive,
  });
  return Boolean(data) || clone.active;
}
