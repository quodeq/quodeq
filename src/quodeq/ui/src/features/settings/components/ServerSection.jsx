import { useState, useEffect, useRef } from 'react';

const HEALTH_POLL_MS = 10000;
const LOG_POLL_MS = 2000;
const MAX_LOG_LINES = 500;
const CONSOLE_POPUP_WIDTH = 800;
const CONSOLE_POPUP_HEIGHT = 500;

function ping() {
  return fetch('/api/health?_t=' + Date.now())
    .then((r) => r.ok ? r.json() : null)
    .catch(() => null);
}

function ConsoleIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="1" y="2" width="14" height="12" rx="2" />
      <polyline points="4.5,6.5 7,9 4.5,11.5" />
      <line x1="9" y1="11" x2="12" y2="11" />
    </svg>
  );
}

export default function ServerSection() {
  const [health, setHealth] = useState(null);
  const [status, setStatus] = useState('checking');
  const [consoleOpen, setConsoleOpen] = useState(false);
  const [logLines, setLogLines] = useState([]);
  const sinceRef = useRef(-1);
  const logRef = useRef(null);
  const healthTimerRef = useRef(null);
  const logTimerRef = useRef(null);
  const cancelledRef = useRef(false);

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

  // Log polling — only when console is open
  useEffect(() => {
    if (!consoleOpen || status !== 'online') {
      clearTimeout(logTimerRef.current);
      return;
    }

    let active = true;

    function pollLogs() {
      const url = '/api/logs' + (sinceRef.current >= 0 ? '?since=' + sinceRef.current : '');
      fetch(url)
        .then((r) => r.ok ? r.json() : null)
        .then((data) => {
          if (!active || !data) return;
          if (data.lines.length) {
            setLogLines((prev) => {
              const next = [...prev, ...data.lines];
              return next.length > MAX_LOG_LINES ? next.slice(-MAX_LOG_LINES) : next;
            });
            sinceRef.current = data.lines[data.lines.length - 1].index;
          }
          logTimerRef.current = setTimeout(pollLogs, LOG_POLL_MS);
        })
        .catch(() => {
          if (active) logTimerRef.current = setTimeout(pollLogs, LOG_POLL_MS);
        });
    }
    pollLogs();

    return () => { active = false; clearTimeout(logTimerRef.current); };
  }, [consoleOpen, status]);

  // Auto-scroll
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [logLines]);

  function handlePopOut() {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.open_browser) {
      window.pywebview.api.open_browser('/logs');
    } else {
      window.open(window.location.origin + '/logs', '_blank', `width=${CONSOLE_POPUP_WIDTH},height=${CONSOLE_POPUP_HEIGHT}`);
    }
  }

  function handleClear() {
    setLogLines([]);
  }

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
        <div className="settings-row">
          <div className="settings-row-label">
            <span className="settings-label">Details</span>
            <span className="settings-description">
              Port <strong>{health.port}</strong> &middot; PID <strong>{health.pid}</strong> &middot; v{health.version}
            </span>
          </div>
        </div>
      )}

      {status === 'online' && (
        <>
          <div
            className="server-console-toggle"
            role="button"
            tabIndex={0}
            onClick={() => setConsoleOpen((o) => !o)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setConsoleOpen((o) => !o); } }}
            aria-label={consoleOpen ? 'Hide console' : 'Show console'}
          >
            <ConsoleIcon />
            <span>Console</span>
            <span className="console-chevron">{consoleOpen ? '\u25BE' : '\u25B8'}</span>
          </div>

          {consoleOpen && (
            <div className="server-console-wrap">
              <div className="console-output" ref={logRef}>
                <pre>
                  {logLines.length
                    ? logLines.map((e) => {
                        const ts = e.timestamp ? e.timestamp.slice(11, 19) : '';
                        return `[${ts}] ${e.line}`;
                      }).join('\n')
                    : 'No logs yet\u2026'}
                </pre>
              </div>
              <div className="server-console-actions">
                <button onClick={handlePopOut}>Pop out</button>
                <button onClick={handleClear}>Clear</button>
              </div>
            </div>
          )}
        </>
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
