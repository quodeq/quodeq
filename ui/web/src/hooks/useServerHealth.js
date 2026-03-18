import { useState, useEffect } from 'react';
import { getHealth } from '../api/index.js';

/**
 * Monitors server connectivity, polling every 5 seconds.
 * When the server is unreachable on the current origin, checks alternate ports
 * and redirects if the server has moved.
 *
 * Returns [serverConnected, setServerConnected].
 */
const DEFAULT_ALT_PORTS = [4180, 4181, 4182, 4183];
const DEFAULT_BASE_URL = 'http://127.0.0.1';
const HEALTH_CHECK_TIMEOUT_MS = 2000;

export function useServerHealth({ altPorts = DEFAULT_ALT_PORTS, baseUrl = DEFAULT_BASE_URL } = {}) {
  const [serverConnected, setServerConnected] = useState(true);

  useEffect(() => {
    let mounted = true;

    async function checkHealth() {
      try {
        await getHealth();
        if (mounted) setServerConnected(true);
      } catch {
        // Server unreachable on current origin — check if it moved to another port
        const currentPort = window.location.port;
        for (const port of altPorts) {
          if (String(port) === currentPort) continue;
          try {
            const ac = new AbortController();
            const tid = setTimeout(() => ac.abort(), HEALTH_CHECK_TIMEOUT_MS);
            const res = await fetch(`${baseUrl}:${port}/api/health`, { signal: ac.signal });
            clearTimeout(tid);
            if (res.ok) {
              window.location.href = `${baseUrl}:${port}`;
              return;
            }
          } catch { /* try next */ }
        }
        if (mounted) setServerConnected(false);
      }
    }
    checkHealth();
    const interval = setInterval(checkHealth, 5000);
    return () => { mounted = false; clearInterval(interval); };
  }, []);

  return [serverConnected, setServerConnected];
}
