import { useState, useEffect } from 'react';
import { getHealth } from '../api/index.js';

/**
 * Monitors server connectivity, polling every 5 seconds.
 * When the server is unreachable on the current origin, checks alternate ports
 * and redirects if the server has moved.
 *
 * Returns [serverConnected, setServerConnected].
 */
export function useServerHealth() {
  const [serverConnected, setServerConnected] = useState(true);

  useEffect(() => {
    let mounted = true;
    const altPorts = [4180, 4181, 4182, 4183];

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
            const res = await fetch(`http://127.0.0.1:${port}/api/health`, { timeout: 2000 });
            if (res.ok) {
              window.location.href = `http://127.0.0.1:${port}`;
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
