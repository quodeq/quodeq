/**
 * Fan-out data hook for the Compare tab: one slim compare-summary query per
 * project. Per-project queries (rather than one fleet endpoint) so rows
 * render progressively, a single cold project can't block the others, and
 * every payload shares the project-scoped cache subtree that dismiss/rescore
 * mutations already invalidate.
 *
 * Standards visibility: every summary is filtered by the SAME source the
 * Overview reads — readVisibleStandardIds(), the browser-local visible set
 * behind the Standards screen's enable/disable stars. Compare used to fetch
 * each project's server-side visibility file instead, which made it deaf to
 * the toggles (the write goes to the SELECTED project only, and 404s
 * silently when that project is a shared one), so flipping a standard never
 * refreshed this screen. One source of truth, and the tab remount re-reads
 * it on every visit.
 */
import { useMemo } from 'react';
import { useQueries, useQuery } from '@tanstack/react-query';
import { getCompareSummary } from '../../../api/index.js';
import { sharedListProjects, sharedGetCompareSummary } from '../../../api/shared.js';
import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';
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

  return useMemo(() => {
    // Read at memo time, not module time: the Standards screen rewrites the
    // set, and returning to Compare remounts this hook (tab subtrees are
    // keyed by tab), so a toggle is always picked up by the next visit.
    const visibleIds = readVisibleStandardIds();
    const summariesById = {};
    const errorsById = {};
    let loadedCount = 0;
    list.forEach((p, i) => {
      const id = p.id || p.name;
      const summary = summaryResults[i];
      if (summary?.data !== undefined) {
        summariesById[id] = applyVisibleStandards(summary.data, visibleIds);
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
  }, [summaryResults]);
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
