import { useQuery } from '@tanstack/react-query';
import { useApi } from '../api/ApiContext.jsx';
import { sharedKeys } from '../api/queryKeys.js';
import { anyActive } from '../api/syncStatus.js';
import { useCloneStatus } from './useCloneStatus.js';

const ACTIVE_MS = 1000;

/**
 * Whether a team-results job (connect, refresh or pull) or a project clone is
 * running right now.
 *
 * Shares the status query with `useSyncStatus` (the strip's poll) and reads
 * its last snapshot, so the top bar can sweep its loading hairline while the
 * strip says "downloading" or "reading projects". While a job is active it
 * also polls on its own: the strip's poll only exists on the Repositories tab
 * and in Settings, and a user who leaves for the overview would otherwise
 * keep a sweeping hairline until they came back. Idle, it never fetches.
 *
 * The clone slot is read passively: the app shell's `useCloneTransitions`
 * polls it, and this hook only ORs its active state in, so the hairline also
 * sweeps while a project clone downloads.
 */
export function useSyncActivity({ activeMs = ACTIVE_MS } = {}) {
  const { getSyncStatus } = useApi();
  const clone = useCloneStatus();
  const { data } = useQuery({
    queryKey: sharedKeys.status(),
    queryFn: getSyncStatus,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchInterval: (query) => (anyActive(query.state.data) ? activeMs : false),
    select: anyActive,
  });
  return Boolean(data) || clone.active;
}
