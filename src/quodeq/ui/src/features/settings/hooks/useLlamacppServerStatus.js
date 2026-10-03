/**
 * useLlamacppServerStatus - TanStack Query poll for llama-server status.
 *
 * Polls every 5s and reports { status: 'online' | 'offline', address }.
 * A fetch rejection is treated as offline.
 */
import { useApi } from '../../../api/ApiContext.jsx';
import { systemKeys } from '../../../api/queryKeys.js';
import { useServerStatusPoll } from './useServerStatusPoll.js';

/**
 * The llama-server status, or null before the first poll resolves.
 *
 * @returns {{status: 'online'|'offline', address: string|null}|null}
 */
export function useLlamacppServerStatus() {
  const { getLlamacppStatus } = useApi();
  return useServerStatusPoll(systemKeys.llamacpp(), getLlamacppStatus, 'useLlamacppServerStatus');
}
