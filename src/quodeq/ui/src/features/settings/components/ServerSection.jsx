import { useState, useEffect, useRef } from 'react';

const POLL_MS = 10000;

function ping() {
  return fetch('/api/health?_t=' + Date.now())
    .then((r) => r.ok ? r.json() : null)
    .catch(() => null);
}

export default function ServerSection() {
  const [health, setHealth] = useState(null);
  const [status, setStatus] = useState('checking');
  const timerRef = useRef(null);
  const cancelledRef = useRef(false);

  useEffect(() => {
    cancelledRef.current = false;

    function tick() {
      ping().then((d) => {
        if (cancelledRef.current) return;
        if (d?.ok) { setHealth(d); setStatus('online'); }
        else { setHealth(null); setStatus('offline'); }
        timerRef.current = setTimeout(tick, POLL_MS);
      });
    }
    tick();

    return () => { cancelledRef.current = true; clearTimeout(timerRef.current); };
  }, []);

  return (
    <section className="panel settings-section">
      <div className="panel-header">
        <h2 className="settings-section-title">Server</h2>
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

      {status === 'online' && health && (
        <div className="settings-row settings-row--last">
          <div className="settings-row-label">
            <span className="settings-label">Details</span>
            <span className="settings-description">
              Port <strong>{health.port}</strong> &middot; PID <strong>{health.pid}</strong> &middot; v{health.version}
            </span>
          </div>
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
