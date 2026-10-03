import { useCallback, useMemo } from 'react';
import { useQueries } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { projectKeys } from '../../../api/queryKeys.js';
import { groupDeferredFindings, markDetailUnavailable, mergeFindingDetail } from '../../../api/complianceDetail.js';
import { FINDING_TYPE } from '../../../vocab/findingType.js';
import { PROJECT_SOURCE } from '../../../vocab/projectSource.js';

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
 * failed come back with `detailUnavailable` set.
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
  return useMemo(
    () => markDetailUnavailable(mergeFindingDetail(items || [], loaded), failed),
    [items, loaded, failed],
  );
}

/**
 * Compliance items with the detail /scores deferred filled back in.
 * @param {Array} items
 * @returns {Array}
 */
export function useHydratedCompliance(items) {
  return useHydratedFindings(items, FINDING_TYPE.COMPLIANCE);
}
