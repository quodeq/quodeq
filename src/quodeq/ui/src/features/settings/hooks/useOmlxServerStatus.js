/**
 * useOmlxServerStatus - TanStack Query poll for omlx server status.
 *
 * Polls every 5s and reports { status: 'online' | 'offline', address }.
 * A fetch rejection is treated as offline.
 */
import { useApi } from '../../../api/ApiContext.jsx';
import { useServerStatusPoll } from './useServerStatusPoll.js';

/**
 * The omlx server status at `baseUrl`, or null before the first poll resolves.
 *
 * @returns {{status: 'online'|'offline', address: string|null}|null}
 */
export function useOmlxServerStatus(baseUrl) {
  const { getOmlxStatus } = useApi();
  return useServerStatusPoll(
    ['system', 'omlx', baseUrl || ''],
    () => getOmlxStatus(baseUrl || undefined),
    'useOmlxServerStatus',
  );
}
