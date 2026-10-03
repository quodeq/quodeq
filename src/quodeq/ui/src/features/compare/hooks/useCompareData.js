/**
 * Data hook for the Compare tab: one slim compare-summary cache entry per
 * project, loaded by one fleet request per source.
 *
 * The entries stay per project so every payload shares the project-scoped
 * cache subtree that dismiss/rescore mutations already invalidate, and one
 * failing project shows an error in its own row. The requests are batched:
 * every entry that needs fetching in the same tick joins one
 * `/fleet/compare` call (see api/fleetCompareLoader.js), so a cold visit
 * costs one request for the local fleet and one for the shared one, and a
 * single invalidated row later costs one request of one project.
 *
 * Standards visibility: every summary is filtered by the SAME source the
 * Overview reads — readVisibleStandardIds(), the browser-local visible set
 * behind the Standards screen's enable/disable stars. Each project's
 * server-side visibility file would miss the toggles (the write goes to the
 * SELECTED project only, and 404s silently when that project is a shared
 * one), so flipping a standard would never refresh this screen. One source
 * of truth, and the tab remount re-reads it on every visit.
 */
import { useMemo } from 'react';
import { useQueries, useQuery } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { makeFleetCompareLoader } from '../../../api/fleetCompareLoader.js';
import { sharedListProjects } from '../../../api/shared.js';
import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';
import { projectKeys, sharedKeys } from '../../../api/queryKeys.js';
import { applyVisibleStandards } from '../compareModel.js';
import { PROJECT_SOURCE } from '../../../vocab/projectSource.js';
import { projectId } from '../../../utils/projectIdentity.js';

// A cold fleet's first response can take as long as its slowest project's
// Overview takes to compute. Match the projects-list ceiling rather than
// the default 30s so slow projects resolve instead of churning.
const COMPARE_SUMMARY_STALE_MS = 60_000;

// One loader per api client and source, so every hook instance on the page
// shares the batch and a test's stub api gets loaders of its own.
const loaders = new WeakMap();

function fleetLoaders(api) {
  let entry = loaders.get(api);
  if (!entry) {
    entry = {
      [PROJECT_SOURCE.LOCAL]: makeFleetCompareLoader((ids) => api.getFleetCompare(ids)),
      [PROJECT_SOURCE.SHARED]: makeFleetCompareLoader((ids) => api.sharedGetFleetCompare(ids)),
    };
    loaders.set(api, entry);
  }
  return entry;
}

const QUERY_DEFAULTS = {
  staleTime: COMPARE_SUMMARY_STALE_MS,
  retry: 1,
  refetchOnWindowFocus: false,
};

/**
 * Fetches one compare summary per project and returns them keyed by row id,
 * alongside the per-project errors so one failing project shows an error in
 * its own row instead of blanking the table.
 *
 * Summaries are filtered by the browser-local visible-standards set, re-read
 * on every mount so a Standards toggle is picked up on the next visit.
 *
 * @returns {{summariesById: object, errorsById: object}}
 */
export function useCompareData(projects) {
  const load = fleetLoaders(useApi());
  const list = (projects || []).filter((p) => p && projectId(p));
  const summaryResults = useQueries({
    queries: list.map((p) => {
      const id = projectId(p);
      // Remote (shared-repo) rows fetch from the shared fleet route with
      // the RAW project id; `id` stays the fleet-unique row key. The key's
      // source segment keeps a same-named local project's cache separate.
      const raw = p.sourceId || id;
      const source = p.source === PROJECT_SOURCE.SHARED ? PROJECT_SOURCE.SHARED : PROJECT_SOURCE.LOCAL;
      return {
        ...QUERY_DEFAULTS,
        queryKey: projectKeys.compareSummary(raw, source),
        queryFn: () => load[source](raw),
      };
    }),
  });

  return useMemo(() => {
    // Read at memo time, not module time: the Standards screen rewrites the
    // set, and returning to Compare remounts this hook (another tab's page
    // took its place meanwhile), so a toggle is always picked up by the
    // next visit.
    const visibleIds = readVisibleStandardIds();
    const summariesById = {};
    const errorsById = {};
    let loadedCount = 0;
    list.forEach((p, i) => {
      const id = projectId(p);
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
    () => (data || []).filter((p) => p && projectId(p)),
    [data],
  );
}
