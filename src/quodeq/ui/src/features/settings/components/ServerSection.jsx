import { useEffect, useRef, useState } from 'react';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import ServerStatusPill from '../../../components/ServerStatusPill.jsx';
import { useServerLog } from '../server-log/ServerLogContext.js';

const HEALTH_POLL_MS = 10000;

function ping() {
  return fetch('/api/health?_t=' + Date.now())
    .then((r) => r.ok ? r.json() : null)
    .catch(() => null);
}


export default function ServerSection() {
  const [health, setHealth] = useState(null);
  const [status, setStatus] = useState('checking');
  const healthTimerRef = useRef(null);
  const cancelledRef = useRef(false);
  const serverLog = useServerLog();

  // Health polling
  useEffect(() => {
    cancelledRef.current = false;

    function tick() {
      ping().then((d) => {
        if (cancelledRef.current) return;
        if (d?.ok) { setHealth(d); setStatus('online'); }
        else { setHealth(null); setStatus('offline'); }
        healthTimerRef.current = setTimeout(tick, HEALTH_POLL_MS);
      });
    }
    tick();

    return () => { cancelledRef.current = true; clearTimeout(healthTimerRef.current); };
  }, []);

  return (
    <section className="panel settings-section">
      <div className="panel-header">
        <SectionLabel marker="▶">Server</SectionLabel>
      </div>

      <ServerStatusPill
        status={status === 'online' ? 'online' : 'offline'}
        address={health?.address}
        offlineMessage={
          status === 'checking'
            ? <span>Checking…</span>
            : <span>Connection lost</span>
        }
        onToggleConsole={() => (serverLog.open ? serverLog.closeLog() : serverLog.openLog())}
        consoleOpen={serverLog.open}
      />

      {status === 'online' && health && (
        <div className="server-details">
          Port <strong>{health.port}</strong>
          {' · '}
          PID <strong>{health.pid}</strong>
          {' · '}
          v{health.version}
        </div>
      )}

      {status === 'offline' && (
        <div className="settings-row settings-row--last">
          <div className="settings-row-label">
            <span className="settings-label">Restart</span>
            <span className="settings-description">
              Stop the server with <code>Ctrl+C</code> in the terminal, then run <code>quodeq dashboard</code> to restart. This page will reconnect automatically.
            </span>
          </div>
        </div>
      )}
    </section>
  );
}
