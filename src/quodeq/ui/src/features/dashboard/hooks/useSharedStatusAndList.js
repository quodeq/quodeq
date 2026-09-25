import { useQuery } from '@tanstack/react-query';
import { sharedStatusQueryOptions, sharedListQueryOptions } from './sharedQueryOptions.js';

/**
 * Observe the shared-repo status and, once it reports a configured repo, the
 * shared project list.
 * @param {Object} params
 * @param {() => Promise<Object>} params.getSharedStatus
 * @param {(opts: {refresh: boolean}) => Promise<Object>} params.sharedListProjects
 * @param {boolean} [params.enabled] Caller gate for both queries.
 * @param {Object} [params.observerOptions] Extra per-observer options for both queries.
 * @returns {{statusQuery: Object, configured: boolean, listQuery: Object}}
 */
export function useSharedStatusAndList({ getSharedStatus, sharedListProjects, enabled, observerOptions }) {
  const statusQuery = useQuery(sharedStatusQueryOptions({ getSharedStatus, enabled, observerOptions }));
  const configured = !!statusQuery.data?.configured;
  const listQuery = useQuery(sharedListQueryOptions({ sharedListProjects, configured, enabled, observerOptions }));
  return { statusQuery, configured, listQuery };
}
