import { useEffect, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useApi } from '../api/ApiContext.jsx';
import { projectsKeys, sharedKeys } from '../api/queryKeys.js';
import { anyActive } from '../api/syncStatus.js';
import { SYNC_KIND, SYNC_PHASE } from '../vocab/syncPhase.js';

const ACTIVE_MS = 1000;
const IDLE_MS = 30000;
const SYNC_KINDS = Object.values(SYNC_KIND);

// `tick` changes on every poll that lands, even when structural sharing hands back the same data object.
function useSyncTransitions(status, tick, queryClient) {
  const prev = useRef(null);
  useEffect(() => {
    if (!status) return;
    const before = prev.current;
    prev.current = status;
    // Only the DONE edge re-lists. The job hydrates the listing during READING;
    // a list request then would run that same cold hydration a second time.
    // A second job of the same kind can start and finish between two polls
    // (DONE -> DONE), so a new finishedAt is an edge too.
    for (const kind of SYNC_KINDS) {
      const was = before?.[kind];
      const now = status[kind];
      if (now?.phase !== SYNC_PHASE.DONE) continue;
      if (was?.phase === SYNC_PHASE.DONE && was.finishedAt === now.finishedAt) continue;
      queryClient.invalidateQueries({ queryKey: sharedKeys.list() });
      // A refresh only re-reads the shared list; connect and pull change what is local or configured.
      if (kind !== SYNC_KIND.REFRESH) queryClient.invalidateQueries({ queryKey: projectsKeys.list() });
    }
  }, [status, tick, queryClient]);
}

/**
 * The one poll of GET /api/shared/status that every sync consumer reads.
 * Polls fast while a connect, refresh or pull job runs and slowly otherwise,
 * and keeps the shared and project lists in step as jobs reach DONE. Mount it
 * once per screen: each mount runs its own transition effect.
 */
export function useSyncStatus({ activeMs = ACTIVE_MS, idleMs = IDLE_MS } = {}) {
  const { getSyncStatus } = useApi();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: sharedKeys.status(),
    queryFn: getSyncStatus,
    refetchOnWindowFocus: false,
    refetchInterval: (q) => (anyActive(q.state.data) ? activeMs : idleMs),
  });
  useSyncTransitions(query.data, query.dataUpdatedAt, queryClient);
  const s = query.data;
  return {
    status: s, configured: Boolean(s?.configured), url: s?.url ?? null, lastSynced: s?.lastSynced ?? null,
    connect: s?.connect, refresh: s?.refresh, pull: s?.pull,
    active: anyActive(s), refetch: query.refetch,
    isLoading: query.isLoading, isError: query.isError, error: query.error,
  };
}
