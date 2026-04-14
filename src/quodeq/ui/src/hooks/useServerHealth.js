import { useState, useEffect } from 'react';
import { getHealth } from '../api/index.js';
import { SERVER_BASE_URL } from '../config.js';

/**
 * Monitors server connectivity, polling every 5 seconds.
 * When the server is unreachable on the current origin, checks alternate ports
 * and redirects if the server has moved.
 *
 * Returns [serverConnected, setServerConnected].
 */
// Standard quodeq port range (4180-4183). The server picks the first
// available port; the client probes alternates when the current one drops.
const DEFAULT_ALT_PORTS = [4180, 4181, 4182, 4183];
const HEALTH_CHECK_TIMEOUT_MS = 2000;
const HEALTH_POLL_INTERVAL_MS = 5000;
const HEALTH_ENDPOINT = '/api/health';

export function useServerHealth({ altPorts = DEFAULT_ALT_PORTS, baseUrl = SERVER_BASE_URL } = {}) {
  const [serverConnected, setServerConnected] = useState(true);

  useEffect(() => {
    let mounted = true;

    async function tryFindPort(candidates) {
      const results = await Promise.allSettled(
        candidates.map(async (port) => {
          const ac = new AbortController();
          const tid = setTimeout(() => ac.abort(), HEALTH_CHECK_TIMEOUT_MS);
          try {
            const res = await fetch(`${baseUrl}:${port}${HEALTH_ENDPOINT}`, { signal: ac.signal });
            clearTimeout(tid);
            if (res.ok) return port;
          } catch { clearTimeout(tid); return null; }
          return null;
        })
      );
      const found = results.find(r => r.status === 'fulfilled' && r.value !== null);
      return found ? found.value : null;
    }

    async function checkHealth() {
      try {
        await getHealth();
        if (mounted) setServerConnected(true);
      } catch {
        const currentPort = window.location.port;
        const foundPort = await tryFindPort(altPorts.filter(p => String(p) !== currentPort));
        if (foundPort) { window.location.href = `${baseUrl}:${foundPort}`; return; }
        if (mounted) setServerConnected(false);
      }
    }
    checkHealth();
    const interval = setInterval(checkHealth, HEALTH_POLL_INTERVAL_MS);
    return () => { mounted = false; clearInterval(interval); };
  }, []);

  return [serverConnected, setServerConnected];
}
