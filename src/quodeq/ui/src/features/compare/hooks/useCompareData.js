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
import { useQueries, useQuery } from '@tanstack/react-query';
import { getCompareSummary } from '../../../api/index.js';
import { sharedListProjects, sharedGetCompareSummary } from '../../../api/shared.js';
import { getStandardsVisibility } from '../../../api/standards.js';
import { projectKeys, sharedKeys } from '../../../api/queryKeys.js';
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
      // Remote (shared-repo) rows fetch from the shared mirror route with
      // the RAW project id; `id` stays the fleet-unique row key. The key's
      // source segment keeps a same-named local project's cache separate.
      const raw = p.sourceId || id;
      const remote = p.source === 'shared';
      return {
        ...QUERY_DEFAULTS,
        queryKey: projectKeys.compareSummary(raw, remote ? 'shared' : 'local'),
        queryFn: () => (remote ? sharedGetCompareSummary(raw) : getCompareSummary(raw)),
      };
    }),
  });
  const visibilityResults = useQueries({
    queries: list.map((p) => {
      const id = p.id || p.name;
      const raw = p.sourceId || id;
      if (p.source === 'shared') {
        // Standards visibility is local per-project configuration; a
        // remote project has none here, so its summary passes unfiltered
        // (exactly the 404 fail-open below, without the request).
        return {
          ...QUERY_DEFAULTS,
          queryKey: projectKeys.standardsVisibility(raw, 'shared'),
          queryFn: async () => ({ visibleStandardIds: null, isDefault: true }),
          staleTime: Infinity,
        };
      }
      return {
        ...QUERY_DEFAULTS,
        queryKey: projectKeys.standardsVisibility(id),
        // A 404 here means the project has no standards context at all
        // (e.g. a mis-registered path with zero runs) — that is "use the
        // defaults", not an error worth retrying.
        queryFn: () => getStandardsVisibility(id).catch((e) => {
          if (e?.status === 404) return { visibleStandardIds: null, isDefault: true };
          throw e;
        }),
        // Visibility is a tiny payload the user can change from the
        // Standards screen at any moment: always re-read on mount (the
        // toggle also invalidates this key) so a disabled standard never
        // lingers on Compare.
        staleTime: 0,
        refetchOnMount: 'always',
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

/**
 * Projects published to the configured shared repository, RAW: the caller
 * merges them against the local list with the Projects page's own
 * precedence rule (projectsMerge.js) before any Compare-specific shaping.
 *
 * No shared repository configured (409), not fetched yet (503), or any
 * other failure all resolve to an empty list: Compare simply shows the
 * local fleet, exactly as before the feature existed.
 */
export function useSharedCompareProjects() {
  const { data } = useQuery({
    queryKey: [...sharedKeys.all(), 'compareProjects'],
    queryFn: () => sharedListProjects().then((r) => r.projects || []).catch(() => []),
    staleTime: COMPARE_SUMMARY_STALE_MS,
    retry: false,
    refetchOnWindowFocus: false,
  });
  return useMemo(
    () => (data || []).filter((p) => p && (p.id || p.name)),
    [data],
  );
}
