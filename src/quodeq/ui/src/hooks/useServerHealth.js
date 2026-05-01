/**
 * useServerHealth — TanStack Query-based connectivity poll.
 *
 * Polls the server every 5s. When the primary endpoint is unreachable,
 * probes alternate quodeq ports (4180-4183) and redirects if the server
 * has moved. Otherwise reports disconnected.
 *
 * Returns [serverConnected, setServerConnected] for backward compatibility.
 * setServerConnected(true) lets the reconnect overlay optimistically clear
 * the disconnected state until the next successful poll.
 */
import { useCallback, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getHealth } from '../api/index.js';
import { SERVER_BASE_URL } from '../config.js';
import { systemKeys } from '../api/queryKeys.js';

const DEFAULT_ALT_PORTS = [4180, 4181, 4182, 4183];
const HEALTH_CHECK_TIMEOUT_MS = 2000;
const HEALTH_POLL_INTERVAL_MS = 5000;
const HEALTH_ENDPOINT = '/api/health';

async function probeAltPort(port, baseUrl) {
  const ac = new AbortController();
  const tid = setTimeout(() => ac.abort(), HEALTH_CHECK_TIMEOUT_MS);
  try {
    const res = await fetch(`${baseUrl}:${port}${HEALTH_ENDPOINT}`, { signal: ac.signal });
    clearTimeout(tid);
    return res.ok ? port : null;
  } catch {
    clearTimeout(tid);
    return null;
  }
}

async function tryFindPort(candidates, baseUrl) {
  const results = await Promise.allSettled(candidates.map((p) => probeAltPort(p, baseUrl)));
  const found = results.find((r) => r.status === 'fulfilled' && r.value !== null);
  return found ? found.value : null;
}

export function useServerHealth({ altPorts = DEFAULT_ALT_PORTS, baseUrl = SERVER_BASE_URL } = {}) {
  // Local override pinned to a specific dataUpdatedAt. setServerConnected(true)
  // optimistically clears the disconnect overlay; once a fresh poll comes
  // in (newer dataUpdatedAt) the override is dropped and the query value wins.
  const [override, setOverride] = useState(null);

  const { data, dataUpdatedAt } = useQuery({
    queryKey: systemKeys.health(),
    queryFn: async () => {
      try {
        await getHealth();
        return true;
      } catch {
        const currentPort = typeof window !== 'undefined' ? window.location.port : '';
        const foundPort = await tryFindPort(
          altPorts.filter((p) => String(p) !== currentPort),
          baseUrl,
        );
        if (foundPort && typeof window !== 'undefined') {
          window.location.href = `${baseUrl}:${foundPort}`;
          // Treat redirect as still-connected to avoid an overlay flash
          // before the page navigates away.
          return true;
        }
        return false;
      }
    },
    refetchInterval: HEALTH_POLL_INTERVAL_MS,
    refetchOnWindowFocus: false,
  });

  const setServerConnected = useCallback((next) => {
    setOverride({ value: Boolean(next), at: Date.now() });
  }, []);

  // The override wins only while it is newer than the latest poll.
  const overrideActive = override !== null && override.at > dataUpdatedAt;
  const effective = overrideActive ? override.value : (data ?? true);

  return [effective, setServerConnected];
}
