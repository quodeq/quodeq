/**
 * Query options for the shared project list. Every screen that reads it uses
 * the same cache entry, so the key and fetcher are defined once here and each
 * caller only adds its own gate or observer options. The status query is
 * polled by hooks/useSyncStatus.js.
 */
import { sharedKeys } from '../../../api/queryKeys.js';

/**
 * Options for the shared project list, fetched without a remote refresh and
 * only once the repo is configured.
 * @param {Object} params
 * @param {(opts: {refresh: boolean}) => Promise<Object>} params.sharedListProjects
 * @param {boolean} params.configured Whether the status query says a repo is connected.
 * @param {boolean} [params.enabled=true] Caller gate, combined with `configured`.
 * @param {Object} [params.observerOptions] Extra per-observer options.
 * @returns {Object}
 */
export function sharedListQueryOptions({ sharedListProjects, configured, enabled = true, observerOptions }) {
  return {
    queryKey: sharedKeys.list(),
    queryFn: () => sharedListProjects({ refresh: false }),
    enabled: enabled && configured,
    ...observerOptions,
  };
}
