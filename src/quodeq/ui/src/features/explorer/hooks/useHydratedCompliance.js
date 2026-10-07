import { useCallback, useEffect, useMemo } from 'react';
import { useQueries, useQueryClient } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { projectKeys } from '../../../api/queryKeys.js';
import {
  groupDeferredFindings, markDetailUnavailable, missingFromDetail, pageSelector, replaceWithDetail,
} from '../../../api/complianceDetail.js';
import { STALE_TIME_MS, refetchWhileError } from '../../../hooks/queryDefaults.js';
import { FINDING_TYPE } from '../../../vocab/findingType.js';
import { PROJECT_SOURCE } from '../../../vocab/projectSource.js';

// When each project's queries were last refreshed because a page's list
// payload named a finding the detail no longer has. One refresh per staleness
// window: the drift is real only until the payload catches up, and a payload
// that never agrees with the detail must not refetch in a loop.
const resyncedAt = new Map();

/** Forget the refresh times (test seam). */
export function resetDetailResyncForTests() {
  resyncedAt.clear();
}

const sourceOf = (ref) => ref.source || PROJECT_SOURCE.LOCAL;

/**
 * Refresh the project's queries when the page's list payload fell behind
 * the detail: a deferred item (file and line) with no row in its loaded
 * group was re-reported, moved or suppressed since the payload was built.
 * The refetched payload reaches the page through the live selectors, and
 * the detail queries refetch with it, since they sit in the project subtree.
 */
function useDriftResync(groups, drifted) {
  const queryClient = useQueryClient();
  useEffect(() => {
    if (!drifted) return;
    const now = Date.now();
    for (const { ref } of groups) {
      const stamp = `${ref.project}\u0000${sourceOf(ref)}`;
      const last = resyncedAt.get(stamp);
      if (last !== undefined && now - last < STALE_TIME_MS) continue;
      resyncedAt.set(stamp, now);
      queryClient.invalidateQueries({ queryKey: projectKeys.project(ref.project, sourceOf(ref)) });
    }
  }, [groups, drifted, queryClient]);
}

/**
 * Refresh an accumulated payload older than its staleness window when the
 * page opens: nothing else refetches it in the desktop webview, whose
 * window never blurs.
 */
function useOpenRefresh(groups) {
  const queryClient = useQueryClient();
  useEffect(() => {
    for (const { ref } of groups) {
      if (ref.run) continue;
      const state = queryClient.getQueryState(projectKeys.scores(ref.project, ref.asOf, PROJECT_SOURCE.LOCAL));
      if (state?.dataUpdatedAt && Date.now() - state.dataUpdatedAt > STALE_TIME_MS) {
        queryClient.invalidateQueries({ queryKey: projectKeys.project(ref.project, PROJECT_SOURCE.LOCAL) });
      }
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps -- the page's opening, once
}

// Where one group's detail lives: the run's lists (/scores/<run> refs carry
// `run` and `source`) or the accumulated ones (/scores refs carry `asOf`).
function detailQuery(api, ref, kind, scope) {
  if (ref.run) {
    const fetchDetail = ref.source === PROJECT_SOURCE.SHARED ? api.sharedGetFindingDetail : api.getFindingDetail;
    return {
      queryKey: projectKeys.runFindingDetail(ref, kind, scope),
      queryFn: () => fetchDetail(ref.project, { kind, dimension: ref.dimension, run: ref.run, ...scope }),
      // A run's rows move only through this client's own mutations, which
      // invalidate the project subtree.
      staleTime: Infinity,
    };
  }
  return {
    queryKey: projectKeys.findingDetail(ref.project, ref.asOf, kind, ref.dimension, scope),
    queryFn: () => api.getFindingDetail(ref.project, { kind, dimension: ref.dimension, asOf: ref.asOf, ...scope }),
    // An as-of view is frozen; the latest view moves with every finished run.
    staleTime: ref.asOf ? Infinity : STALE_TIME_MS,
  };
}

/**
 * The rows a page renders for *items*, with the detail /scores, /scores/<run>
 * or /eval deferred: each loaded group's deferred items are replaced by the
 * rows the server holds for it (api/complianceDetail.js replaceWithDetail).
 *
 * Returns *items* unchanged while the detail loads (the cards show a
 * skeleton for a deferred item), or when none of them is deferred. Items
 * whose detail fetch failed come back with `detailUnavailable` set and the
 * query retries on its own. A refetch keeps the rows it replaces on screen,
 * and a payload the detail no longer agrees with refreshes the project's
 * queries (useDriftResync).
 * @param {Array} items
 * @param {string} kind FINDING_TYPE.VIOLATION or FINDING_TYPE.COMPLIANCE
 * @param {{select?: (row: Object) => boolean}} [options] which of the group's
 *   rows belong on the page; defaults to the fields *items* are unanimous on.
 * @returns {Array}
 */
export function useHydratedFindings(items, kind, { select } = {}) {
  const api = useApi();
  const groups = useMemo(() => groupDeferredFindings(items), [items]);
  const selectRow = useMemo(() => select || pageSelector(items || []), [select, items]);
  const combine = useCallback((results) => ({
    loaded: results.flatMap((r, i) => (r.data ? [{ ref: groups[i].ref, items: r.data }] : [])),
    failed: results.flatMap((r, i) => (r.isError && !r.data ? [groups[i].ref] : [])),
  }), [groups]);
  const { loaded, failed } = useQueries({
    queries: groups.map(({ ref, scope }) => ({ ...detailQuery(api, ref, kind, scope), refetchInterval: refetchWhileError })),
    combine,
  });
  const { hydrated, drifted } = useMemo(() => ({
    hydrated: markDetailUnavailable(replaceWithDetail(items || [], loaded, selectRow), failed),
    drifted: missingFromDetail(items || [], loaded, selectRow),
  }), [items, loaded, failed, selectRow]);
  useDriftResync(groups, drifted);
  useOpenRefresh(groups);
  return hydrated;
}

/**
 * Compliance items with the detail /scores deferred filled back in.
 * @param {Array} items
 * @param {{select?: (row: Object) => boolean}} [options]
 * @returns {Array}
 */
export function useHydratedCompliance(items, options) {
  return useHydratedFindings(items, FINDING_TYPE.COMPLIANCE, options);
}
