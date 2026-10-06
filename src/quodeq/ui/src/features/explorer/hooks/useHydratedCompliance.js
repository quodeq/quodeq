import { useCallback, useEffect, useMemo } from 'react';
import { useQueries, useQueryClient } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { projectKeys } from '../../../api/queryKeys.js';
import { groupDeferredFindings, markDetailOutdated, markDetailUnavailable, mergeFindingDetail } from '../../../api/complianceDetail.js';
import { STALE_TIME_MS } from '../../../hooks/queryDefaults.js';
import { FINDING_TYPE } from '../../../vocab/findingType.js';
import { PROJECT_SOURCE } from '../../../vocab/projectSource.js';

// (project, generation) pairs whose scores were already invalidated because a
// page found outdated items: one refresh per snapshot, not one per render.
const resynced = new Set();

/** Forget which snapshots were already refreshed (test seam). */
export function resetDetailResyncForTests() {
  resynced.clear();
}

// Accumulated refs (/scores) carry `asOf`; run refs carry `run` and are
// immutable, so only the accumulated ones can go stale.
function accumulatedRefs(groups) {
  return groups.map((g) => g.ref).filter((ref) => !ref.run);
}

/**
 * Keep the page's snapshot in step with the server. The File and Principle
 * pages render findings built when the user clicked, from the app-root
 * /scores payload, while the detail is fetched from the server's current
 * state. Two cases make the two disagree, and both refresh the project's
 * queries so the snapshot catches up: a loaded group without a row for an
 * item (the finding changed since; once per snapshot generation), and a
 * payload older than its staleness window when the page opens (nothing else
 * refetches it in the desktop webview).
 */
function useSnapshotResync(groups, hydrated) {
  const queryClient = useQueryClient();
  const outdated = hydrated.some((item) => item?.detailOutdated);
  useEffect(() => {
    if (!outdated) return;
    for (const ref of accumulatedRefs(groups)) {
      const stamp = `${ref.project}\u0000${ref.generation}`;
      if (resynced.has(stamp)) continue;
      resynced.add(stamp);
      queryClient.invalidateQueries({ queryKey: projectKeys.project(ref.project, PROJECT_SOURCE.LOCAL) });
    }
  }, [groups, outdated, queryClient]);
  useEffect(() => {
    for (const ref of accumulatedRefs(groups)) {
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
    };
  }
  return {
    queryKey: projectKeys.findingDetail(ref.project, ref.asOf, kind, ref.dimension, ref.generation, scope),
    queryFn: () => api.getFindingDetail(ref.project, { kind, dimension: ref.dimension, asOf: ref.asOf, ...scope }),
  };
}

/**
 * Items of one kind with the detail /scores or /scores/<run> deferred
 * filled back in.
 *
 * Returns *items* unchanged while the detail loads, or when none of them is
 * deferred (items from /eval already carry it). Items whose detail fetch
 * failed come back with `detailUnavailable` set; items whose group loaded
 * without a row for them come back with `detailOutdated` set, and the
 * project's scores are refreshed so the page's snapshot catches up (see
 * useSnapshotResync).
 * @param {Array} items
 * @param {string} kind FINDING_TYPE.VIOLATION or FINDING_TYPE.COMPLIANCE
 * @returns {Array}
 */
export function useHydratedFindings(items, kind) {
  const api = useApi();
  const groups = useMemo(() => groupDeferredFindings(items), [items]);
  const combine = useCallback((results) => ({
    loaded: results.flatMap((r, i) => (r.data ? [{ ref: groups[i].ref, items: r.data }] : [])),
    failed: results.flatMap((r, i) => (r.isError ? [groups[i].ref] : [])),
  }), [groups]);
  const { loaded, failed } = useQueries({
    queries: groups.map(({ ref, scope }) => ({
      ...detailQuery(api, ref, kind, scope),
      // Keyed on the scores response generation, so an entry can never go stale.
      staleTime: Infinity,
    })),
    combine,
  });
  const hydrated = useMemo(() => {
    const merged = mergeFindingDetail(items || [], loaded);
    return markDetailUnavailable(markDetailOutdated(merged, loaded.map((l) => l.ref)), failed);
  }, [items, loaded, failed]);
  useSnapshotResync(groups, hydrated);
  return hydrated;
}

/**
 * Compliance items with the detail /scores deferred filled back in.
 * @param {Array} items
 * @returns {Array}
 */
export function useHydratedCompliance(items) {
  return useHydratedFindings(items, FINDING_TYPE.COMPLIANCE);
}
