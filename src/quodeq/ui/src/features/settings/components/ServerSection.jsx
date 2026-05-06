import { useQuery } from '@tanstack/react-query';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import ServerStatusPill from '../../../components/ServerStatusPill.jsx';
import HelpHint from '../../../components/HelpHint.jsx';
import { useServerLog } from '../server-log/ServerLogContext.js';
import { systemKeys } from '../../../api/queryKeys.js';

const LOCAL_SERVER_HINT = (
  <>
    This server runs entirely on your own machine, so nothing leaves your computer. Quodeq is a local-first app that respects your privacy.
  </>
);

const HEALTH_POLL_MS = 10000;

async function ping() {
  try {
    const res = await fetch('/api/health?_t=' + Date.now());
    if (!res.ok) return null;
    const data = await res.json();
    return data?.ok ? data : null;
  } catch {
    return null;
  }
}

export default function ServerSection() {
  const serverLog = useServerLog();

  const { data: health, isLoading } = useQuery({
    queryKey: [...systemKeys.health(), 'settings-detail'],
    queryFn: ping,
    refetchInterval: HEALTH_POLL_MS,
    refetchOnWindowFocus: false,
  });

  const status = isLoading && !health ? 'checking' : (health ? 'online' : 'offline');

  return (
    <section className="panel settings-section">
      <div className="panel-header">
        <span className="settings-label-row">
          <SectionLabel marker="▶">Local server</SectionLabel>
          <HelpHint label="Local server help">{LOCAL_SERVER_HINT}</HelpHint>
        </span>
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
