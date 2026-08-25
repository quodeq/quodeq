/**
 * Fan-out data hook for the Compare tab: per local project, one query for
 * the slim compare-summary and one for the project's enabled-standards set.
 * Per-project queries (rather than one fleet endpoint) so rows render
 * progressively, a single cold project can't block the others, and every
 * payload shares the project-scoped cache subtree that dismiss/rescore
 * mutations already invalidate.
 *
 * Each summary is filtered to the project's own visible standards before it
 * leaves this hook (same utils the Overview uses), so Compare never shows a
 * dimension the project has disabled.
 */
import { useMemo } from 'react';
import { useQueries } from '@tanstack/react-query';
import { getCompareSummary } from '../../../api/index.js';
import { getStandardsVisibility } from '../../../api/standards.js';
import { projectKeys } from '../../../api/queryKeys.js';
import { applyVisibleStandards } from '../compareModel.js';

// A cold project's first summary can take as long as its Overview takes to
// compute (the accumulated walk). Match the projects-list ceiling rather
// than the default 30s so slow projects resolve instead of churning.
const COMPARE_SUMMARY_STALE_MS = 60_000;

const QUERY_DEFAULTS = {
  staleTime: COMPARE_SUMMARY_STALE_MS,
  retry: 1,
  refetchOnWindowFocus: false,
};

export function useCompareData(projects) {
  const list = (projects || []).filter((p) => p && (p.id || p.name));
  const summaryResults = useQueries({
    queries: list.map((p) => {
      const id = p.id || p.name;
      return {
        ...QUERY_DEFAULTS,
        queryKey: projectKeys.compareSummary(id),
        queryFn: () => getCompareSummary(id),
      };
    }),
  });
  const visibilityResults = useQueries({
    queries: list.map((p) => {
      const id = p.id || p.name;
      return {
        ...QUERY_DEFAULTS,
        queryKey: projectKeys.standardsVisibility(id),
        queryFn: () => getStandardsVisibility(id),
      };
    }),
  });

  return useMemo(() => {
    const summariesById = {};
    const errorsById = {};
    let loadedCount = 0;
    list.forEach((p, i) => {
      const id = p.id || p.name;
      const summary = summaryResults[i];
      const visibility = visibilityResults[i];
      // A row counts as loaded once BOTH queries settled — otherwise hidden
      // dimensions would flash in and then disappear when the visibility
      // arrives. A failed visibility fetch fails open (unfiltered data
      // beats a blank row); a failed summary is a real row error.
      const visibilitySettled = visibility?.data !== undefined || visibility?.isError;
      if (summary?.data !== undefined && visibilitySettled) {
        summariesById[id] = applyVisibleStandards(
          summary.data,
          visibility?.data?.visibleStandardIds ?? null,
        );
        loadedCount += 1;
      } else if (summary?.isError) {
        errorsById[id] = summary.error;
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [summaryResults, visibilityResults]);
}
