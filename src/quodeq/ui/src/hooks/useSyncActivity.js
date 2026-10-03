import { useQuery } from '@tanstack/react-query';
import { useApi } from '../api/ApiContext.jsx';
import { sharedKeys } from '../api/queryKeys.js';
import { anyActive } from '../api/syncStatus.js';

const ACTIVE_MS = 1000;

/**
 * Whether a team-results job (connect, refresh or pull) is running right now.
 *
 * Shares the status query with `useSyncStatus` (the strip's poll) and reads
 * its last snapshot, so the top bar can sweep its loading hairline while the
 * strip says "downloading" or "reading projects". While a job is active it
 * also polls on its own: the strip's poll only exists on the Repositories tab
 * and in Settings, and a user who leaves for the overview would otherwise
 * keep a sweeping hairline until they came back. Idle, it never fetches.
 */
export function useSyncActivity({ activeMs = ACTIVE_MS } = {}) {
  const { getSyncStatus } = useApi();
  const { data } = useQuery({
    queryKey: sharedKeys.status(),
    queryFn: getSyncStatus,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchInterval: (query) => (anyActive(query.state.data) ? activeMs : false),
    select: anyActive,
  });
  return Boolean(data);
}
