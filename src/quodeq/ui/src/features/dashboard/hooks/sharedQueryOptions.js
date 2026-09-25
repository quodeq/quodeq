/**
 * Query options for the shared repo's status and project list. Every screen
 * that reads them uses the same cache entries, so the keys and fetchers are
 * defined once here and each caller only adds its own gate or observer
 * options.
 */
import { sharedKeys } from '../../../api/queryKeys.js';

/**
 * Options for the shared-repo status query.
 * @param {Object} params
 * @param {() => Promise<Object>} params.getSharedStatus
 * @param {boolean} [params.enabled] Caller gate; left unset when omitted.
 * @param {Object} [params.observerOptions] Extra per-observer options.
 * @returns {Object}
 */
export function sharedStatusQueryOptions({ getSharedStatus, enabled, observerOptions }) {
  return {
    queryKey: sharedKeys.status(),
    queryFn: getSharedStatus,
    ...(enabled === undefined ? {} : { enabled }),
    ...observerOptions,
  };
}

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
