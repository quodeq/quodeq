import { useQuery } from '@tanstack/react-query';
import { projectKeys } from '../../../api/queryKeys.js';
import { request } from '../../../api/request.js';

/**
 * Pre-run scan estimates for the setup card: per-dimension file counts plus
 * cached/changed/project totals. One fetch covers both scan modes — each
 * dimension carries `count` (incremental queue) and `total` (clean queue),
 * so mode toggles never refetch.
 *
 * Best-effort: estimates are decoration on the form, so errors resolve to
 * null and the card falls back to numberless copy.
 * @returns {{estimates: object|null, loading: boolean}}
 */
export function useScanEstimates(projectId, enabled = true) {
  const { data, isLoading } = useQuery({
    queryKey: [...projectKeys.project(projectId || ''), 'estimates'],
    queryFn: ({ signal }) => request(`/projects/${encodeURIComponent(projectId)}/estimates`, { signal }),
    enabled: !!projectId && enabled,
    staleTime: 60_000,
    retry: false,
  });
  return { estimates: data ?? null, loading: !!projectId && enabled && isLoading };
}
