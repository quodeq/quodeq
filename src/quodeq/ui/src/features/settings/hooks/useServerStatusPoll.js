/**
 * useServerStatusPoll - the TanStack Query poll every local-provider server
 * status hook runs (Ollama, llama.cpp, omlx): only the query key, the fetch
 * call and the warning label differ between them.
 *
 * Polls every 5s and reports { status: 'online' | 'offline', address }.
 * A fetch rejection is treated as offline.
 */
import { useQuery } from '@tanstack/react-query';
import { SERVER_STATUS } from '../settingsVocab.js';

const POLL_MS = 5000;

/**
 * @param {Array} queryKey React Query key for this poll.
 * @param {() => Promise<{running?: boolean, address?: string}>} fetchStatus
 * @param {string} label Console-warning tag for a failed poll.
 * @returns {{status: 'online'|'offline', address: string|null}|null}
 */
export function useServerStatusPoll(queryKey, fetchStatus, label) {
  const { data } = useQuery({
    queryKey,
    queryFn: async () => {
      try {
        const result = await fetchStatus();
        if (result?.running) {
          return { status: SERVER_STATUS.ONLINE, address: result.address ?? null };
        }
        return { status: SERVER_STATUS.OFFLINE, address: null };
      } catch (err) {
        console.warn(`[${label}] status poll failed:`, err);
        return { status: SERVER_STATUS.OFFLINE, address: null };
      }
    },
    refetchInterval: POLL_MS,
    refetchOnWindowFocus: false,
  });

  return data ?? null;
}
