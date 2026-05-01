/**
 * useOllamaServerStatus — TanStack Query poll for Ollama daemon status.
 *
 * Polls every 5s and reports { status: 'online' | 'offline', address }.
 * A fetch rejection is treated as offline.
 */
import { useQuery } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { systemKeys } from '../../../api/queryKeys.js';

const POLL_MS = 5000;

export function useOllamaServerStatus() {
  const { getOllamaStatus } = useApi();

  const { data } = useQuery({
    queryKey: systemKeys.ollama(),
    queryFn: async () => {
      try {
        const result = await getOllamaStatus();
        if (result?.running) {
          return { status: 'online', address: result.address ?? null };
        }
        return { status: 'offline', address: null };
      } catch {
        return { status: 'offline', address: null };
      }
    },
    refetchInterval: POLL_MS,
    refetchOnWindowFocus: false,
  });

  return data ?? null;
}
