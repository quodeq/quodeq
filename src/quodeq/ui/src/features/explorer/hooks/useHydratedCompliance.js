import { useCallback, useMemo } from 'react';
import { useQueries } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { projectKeys } from '../../../api/queryKeys.js';
import { groupDeferredCompliance, mergeComplianceDetail } from '../../../api/complianceDetail.js';

/**
 * Compliance items with the detail /scores deferred filled back in.
 *
 * Returns *items* unchanged while the detail loads, or when none of them is
 * deferred (items from /eval or a shared project already carry it).
 * @param {Array} items
 * @returns {Array}
 */
export function useHydratedCompliance(items) {
  const { getComplianceDetail } = useApi();
  const groups = useMemo(() => groupDeferredCompliance(items), [items]);

  const combine = useCallback((results) => results.flatMap((r, i) => (
    r.data ? [{ ref: groups[i].ref, items: r.data }] : []
  )), [groups]);

  const loaded = useQueries({
    queries: groups.map(({ ref, scope }) => ({
      queryKey: projectKeys.complianceDetail(ref.project, ref.asOf, ref.dimension, ref.generation, scope),
      queryFn: () => getComplianceDetail(ref.project, { dimension: ref.dimension, asOf: ref.asOf, ...scope }),
      // Keyed on the /scores response generation, so an entry can never go stale.
      staleTime: Infinity,
    })),
    combine,
  });

  return useMemo(() => mergeComplianceDetail(items || [], loaded), [items, loaded]);
}
