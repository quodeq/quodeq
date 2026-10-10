import { useQuery, useQueryClient } from '@tanstack/react-query';
import { projectsKeys } from '../../api/queryKeys.js';

/**
 * The server's warm-up snapshot as the project list last reported it:
 * `{active, projectsDone, projectsTotal, currentProjectName}` (see
 * services/warmup.py snapshot), or null before the first list or when the
 * server sent none. The list writes it (hooks/useProjectState.js) on every
 * fetch, and the list already polls every few seconds while any card is
 * pending, which is exactly while the warm-up runs: no request of its own.
 */

/**
 * Record the snapshot that rode on a project list response.
 * @param {import('@tanstack/react-query').QueryClient} queryClient
 * @param {Object|null} warmup
 */
export function recordWarmupSnapshot(queryClient, warmup) {
  queryClient.setQueryData(projectsKeys.warmup(), warmup ?? null);
}

/** @returns {Object|null} the last recorded snapshot; re-renders when the list records a new one */
export function useWarmupSnapshot() {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: projectsKeys.warmup(),
    // Never fetched: the list route records it. The initial read is the
    // cache's current value so a strip mounted after the first list sees it.
    queryFn: () => queryClient.getQueryData(projectsKeys.warmup()) ?? null,
    enabled: false,
    staleTime: Infinity,
    gcTime: Infinity,
  });
  return data ?? null;
}
