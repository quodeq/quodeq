/**
 * useOmlxServerStatus - TanStack Query poll for omlx server status.
 *
 * Polls every 5s and reports { status: 'online' | 'offline', address }.
 * A fetch rejection is treated as offline.
 */
import { useQuery } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';

const POLL_MS = 5000;
const SERVER_STATUS = { ONLINE: 'online', OFFLINE: 'offline' };
// What every non-running answer resolves to, including a failed poll.
const OFFLINE_RESULT = { status: SERVER_STATUS.OFFLINE, address: null };

/**
 * The omlx server status at `baseUrl`, or null before the first poll resolves.
 *
 * @returns {{status: 'online'|'offline', address: string|null}|null}
 */
export function useOmlxServerStatus(baseUrl) {
  const { getOmlxStatus } = useApi();

  const { data } = useQuery({
    queryKey: ['system', 'omlx', baseUrl || ''],
    queryFn: async () => {
      try {
        const result = await getOmlxStatus(baseUrl || undefined);
        if (result?.running) {
          return { status: SERVER_STATUS.ONLINE, address: result.address ?? null };
        }
        return OFFLINE_RESULT;
      } catch (err) {
        console.warn('[useOmlxServerStatus] status poll failed:', err);
        return OFFLINE_RESULT;
      }
    },
    refetchInterval: POLL_MS,
    refetchOnWindowFocus: false,
  });

  return data ?? null;
}
