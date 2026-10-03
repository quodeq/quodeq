import { useQuery } from '@tanstack/react-query';
import { useApi } from '../api/ApiContext.jsx';
import { sharedKeys } from '../api/queryKeys.js';
import { anyActive } from '../api/syncStatus.js';

/**
 * Whether a team-results job (connect, refresh or pull) is running right now.
 *
 * A passive observer of the shared status query: it never polls on its own
 * (the screen that shows the sync, `useSyncStatus`, does) and only reads
 * what that poll put in the cache, so the top bar can sweep its loading
 * hairline while the strip says "downloading" or "reading projects".
 */
export function useSyncActivity() {
  const { getSyncStatus } = useApi();
  const { data } = useQuery({
    queryKey: sharedKeys.status(),
    queryFn: getSyncStatus,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    select: anyActive,
  });
  return Boolean(data);
}
