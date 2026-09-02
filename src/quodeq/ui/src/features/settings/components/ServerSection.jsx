import { useQuery } from '@tanstack/react-query';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import ServerStatusPill from '../../../components/ServerStatusPill.jsx';
import HelpHint from '../../../components/HelpHint.jsx';
import { useServerLog } from '../server-log/ServerLogContext.js';
import { systemKeys } from '../../../api/queryKeys.js';
import { getHealth } from '../../../api/index.js';
import { t } from '../../../strings/index.js';
import { tRich } from '../../../strings/rich.jsx';

const LOCAL_SERVER_HINT = t('settings.localServerHint');

const HEALTH_POLL_MS = 10000;

function ServerDetails({ health }) {
  return (
    <div className="server-details">
      {t('settings.serverPortLabel')} <strong>{health.port}</strong>
      {' · '}
      {t('settings.serverPidLabel')} <strong>{health.pid}</strong>
      {' · '}
      {t('settings.serverVersion', { version: health.version })}
    </div>
  );
}

function OfflineRestartHint() {
  return (
    <div className="settings-row settings-row--last">
      <div className="settings-row-label">
        <span className="settings-label">{t('settings.restart')}</span>
        <span className="settings-description">
          {tRich('settings.restartDesc')}
        </span>
      </div>
    </div>
  );
}

export default function ServerSection() {
  const serverLog = useServerLog();

  const { data: health, isLoading } = useQuery({
    queryKey: [...systemKeys.health(), 'settings-detail'],
    queryFn: () => getHealth().then((d) => (d?.ok ? d : null)).catch(() => null),
    refetchInterval: HEALTH_POLL_MS,
    refetchOnWindowFocus: false,
  });

  const status = isLoading && !health ? 'checking' : (health ? 'online' : 'offline');

  return (
    <section className="panel settings-section">
      <div className="panel-header">
        <span className="settings-label-row">
          <SectionLabel marker="▶">{t('settings.localServerLabel')}</SectionLabel>
          <HelpHint label={t('settings.localServerHelpAria')}>{LOCAL_SERVER_HINT}</HelpHint>
        </span>
      </div>

      <ServerStatusPill
        status={status === 'online' ? 'online' : 'offline'}
        address={health?.address}
        offlineMessage={
          status === 'checking'
            ? <span>{t('settings.checkingEllipsis')}</span>
            : <span>{t('settings.connectionLost')}</span>
        }
        onToggleConsole={() => (serverLog.open ? serverLog.closeLog() : serverLog.openLog())}
        consoleOpen={serverLog.open}
      />

      {status === 'online' && health && <ServerDetails health={health} />}

      {status === 'offline' && <OfflineRestartHint />}
    </section>
  );
}
