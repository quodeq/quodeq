import { useState } from 'react';
import { useApi } from '../api/ApiContext.jsx';
import { t } from '../strings/index.js';

// The shell command to restart the server: identity, not translatable copy.
// The literal command to type. Not copy: translating it would print a
// command that does not exist.
// eslint-disable-next-line i18n/no-prose-literals
const RESTART_COMMAND = 'quodeq dashboard';

// A wedged server accepts the connection and never answers; the default
// request timeout would hold the retry button for 30 s with no sign.
const HEALTH_PROBE_TIMEOUT_MS = 5000;

export default function ServerDisconnectedOverlay({ onReconnect }) {
  const { getHealth } = useApi();
  const [checking, setChecking] = useState(false);
  const [failed, setFailed] = useState(false);

  async function retry() {
    setChecking(true);
    setFailed(false);
    try {
      await getHealth({ timeout: HEALTH_PROBE_TIMEOUT_MS });
      onReconnect();
    } catch (err) {
      console.warn('Reconnect failed:', err);
      setFailed(true);
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="server-disconnected-overlay">
      <div className="server-disconnected-card">
        <div className="server-disconnected-icon">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="1" y1="1" x2="23" y2="23" />
            <path d="M16.72 11.06A10.94 10.94 0 0 1 19 12.55" />
            <path d="M5 12.55a10.94 10.94 0 0 1 5.17-2.39" />
            <path d="M10.71 5.05A16 16 0 0 1 22.56 9" />
            <path d="M1.42 9a15.91 15.91 0 0 1 4.7-2.88" />
            <path d="M8.53 16.11a6 6 0 0 1 6.95 0" />
            <line x1="12" y1="20" x2="12.01" y2="20" />
          </svg>
        </div>
        <h2>{t('common.serverDisconnected')}</h2>
        <p>{t('common.serverDisconnectedBody')}</p>
        <code>{RESTART_COMMAND}</code>
        {failed && <p className="server-retry-status" role="status">{t('common.stillUnreachable')}</p>}
        <button type="button" className="server-retry-btn" onClick={retry} disabled={checking}>
          {checking ? t('common.checkingConnection') : t('common.retryConnection')}
        </button>
      </div>
    </div>
  );
}
