import { useState, useEffect, useRef } from 'react';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import { useServerLog } from '../server-log/ServerLogContext.js';
import ConsoleButton from '../../../components/ConsoleButton.jsx';

const HEALTH_POLL_MS = 10000;

function ping() {
  return fetch('/api/health?_t=' + Date.now())
    .then((r) => r.ok ? r.json() : null)
    .catch(() => null);
}


export default function ServerSection() {
  const [health, setHealth] = useState(null);
  const [status, setStatus] = useState('checking');
  const [detailsOpen, setDetailsOpen] = useState(false);
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

      <div className={`server-status ${status === 'online' ? 'server-status--online' : 'server-status--offline'}`}>
        <span className={`server-dot ${status === 'online' ? 'server-dot--online' : 'server-dot--offline'}`} />
        <span>
          {status === 'online' && 'Running'}
          {status === 'offline' && 'Connection lost'}
          {status === 'checking' && 'Checking...'}
        </span>
        {status === 'online' && health?.address && <span className="server-address">{health.address}</span>}
      </div>

      {/* Server details (port, PID, version) are intentionally available
          for this local-only development tool to aid debugging. They are
          hidden by default behind a toggle to avoid casual disclosure. */}
      {status === 'online' && health && (
        <div className="settings-row">
          <div className="settings-row-label">
            <span
              className="settings-label"
              role="button"
              tabIndex={0}
              style={{ cursor: 'pointer' }}
              onClick={() => setDetailsOpen((o) => !o)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setDetailsOpen((o) => !o); } }}
            >
              Details {detailsOpen ? '▾' : '▸'}
            </span>
            {detailsOpen && (
              <span className="settings-description">
                Port <strong>{health.port}</strong> &middot; PID <strong>{health.pid}</strong> &middot; v{health.version}
              </span>
            )}
          </div>
        </div>
      )}

      {status === 'online' && (
        <ConsoleButton
          open={serverLog.open}
          onToggle={() => (serverLog.open ? serverLog.closeLog() : serverLog.openLog())}
        />
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
