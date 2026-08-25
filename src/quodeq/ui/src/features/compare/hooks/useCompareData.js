/**
 * Fan-out data hook for the Compare tab: one query per local project against
 * the slim compare-summary endpoint. Per-project queries (rather than one
 * fleet endpoint) so rows render progressively, a single cold project can't
 * block the others, and every summary shares the project-scoped cache
 * subtree that dismiss/rescore mutations already invalidate.
 */
import { useQueries } from '@tanstack/react-query';
import { getCompareSummary } from '../../../api/index.js';
import { projectKeys } from '../../../api/queryKeys.js';

// A cold project's first summary can take as long as its Overview takes to
// compute (the accumulated walk). Match the projects-list ceiling rather
// than the default 30s so slow projects resolve instead of churning.
const COMPARE_SUMMARY_STALE_MS = 60_000;

export function useCompareData(projects) {
  const list = (projects || []).filter((p) => p && (p.id || p.name));
  const results = useQueries({
    queries: list.map((p) => {
      const id = p.id || p.name;
      return {
        queryKey: projectKeys.compareSummary(id),
        queryFn: () => getCompareSummary(id),
        staleTime: COMPARE_SUMMARY_STALE_MS,
        retry: 1,
        // Projects without runs still 200 with an empty shape, so an error
        // here is a real failure worth surfacing on the row.
        refetchOnWindowFocus: false,
      };
    }),
  });

  const summariesById = {};
  const errorsById = {};
  let loadedCount = 0;
  list.forEach((p, i) => {
    const id = p.id || p.name;
    const r = results[i];
    if (r?.data !== undefined) {
      summariesById[id] = r.data;
      loadedCount += 1;
    } else if (r?.isError) {
      errorsById[id] = r.error;
      loadedCount += 1;
    }
  });

  return {
    summariesById,
    errorsById,
    loadedCount,
    totalCount: list.length,
    isLoading: list.length > 0 && loadedCount === 0,
    allLoaded: loadedCount === list.length,
  };
}
