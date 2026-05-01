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
  // Local state is the source of truth for callers. The query side-effects
  // it on each poll resolution. setServerConnected(true) lets the reconnect
  // overlay optimistically clear the disconnected state until the next poll.
  const [connected, setConnected] = useState(true);
  const [version, setVersion] = useState(null);

  useQuery({
    queryKey: systemKeys.health(),
    queryFn: async () => {
      try {
        const data = await getHealth();
        setConnected(true);
        if (data?.version) setVersion(data.version);
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
          setConnected(true);
          return true;
        }
        setConnected(false);
        return false;
      }
    },
    refetchInterval: HEALTH_POLL_INTERVAL_MS,
    refetchOnWindowFocus: false,
  });

  const setServerConnected = useCallback((next) => {
    setConnected(Boolean(next));
  }, []);

  return [connected, setServerConnected, version];
}
