/**
 * Query options for the shared project list. Every screen that reads it uses
 * the same cache entry, so the key and fetcher are defined once here and each
 * caller only adds its own gate or observer options. The status query is
 * polled by hooks/useSyncStatus.js.
 */
import { sharedKeys } from '../../../api/queryKeys.js';
import { SYNC_ACTIVE_PHASES } from '../../../vocab/syncPhase.js';

// Same test as api/syncStatus.js isSlotActive, read straight off the vocab:
// that module pulls in the request client, which node --test cannot load.
function connectActive(status) {
  return SYNC_ACTIVE_PHASES.has(status?.connect?.phase);
}

/**
 * Options for the shared project list, fetched without a remote refresh and
 * only once the repo is configured and no connect is still working.
 *
 * The server saves the settings before a connect job reads the clone, so
 * `configured` turns true while the job is still hydrating the listing. A
 * list request then would run that same cold hydration a second time, so the
 * list waits for the connect to finish; the DONE edge fetches it. A running
 * refresh or pull does not gate it: the listing already on screen stays valid.
 * @param {Object} params
 * @param {(opts: {refresh: boolean}) => Promise<Object>} params.sharedListProjects
 * @param {boolean} params.configured Whether the status query says a repo is connected.
 * @param {Object} [params.status] The GET /shared/status payload, for its connect slot.
 * @param {boolean} [params.enabled=true] Caller gate, combined with `configured`.
 * @param {Object} [params.observerOptions] Extra per-observer options.
 * @returns {Object}
 */
export function sharedListQueryOptions({ sharedListProjects, configured, status, enabled = true, observerOptions }) {
  return {
    queryKey: sharedKeys.list(),
    queryFn: () => sharedListProjects({ refresh: false }),
    enabled: enabled && configured && !connectActive(status),
    refetchInterval: summaryRefetchInterval,
    ...observerOptions,
  };
}

/** How often the list re-asks while a card's summary is still being computed. */
export const SUMMARY_POLL_MS = 3000;

// The server lists a cold card as pending and warms it in the background
// (the same contract as the local list), so the list re-asks every few
// seconds while any card is pending and the grades fill in as they land;
// otherwise it does not poll.
function summaryRefetchInterval(query) {
  return query.state.data?.projects?.some((p) => p.summaryPending) ? SUMMARY_POLL_MS : false;
}
