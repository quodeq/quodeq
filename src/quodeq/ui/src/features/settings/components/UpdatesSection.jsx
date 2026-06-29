import { useState } from 'react';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import { checkForUpdates, setUpdateAutoCheck } from '../../../api/index.js';
import { useUpdateStatus } from '../../updates/useUpdateStatus.js';
import { openExternal } from '../../updates/openExternal.js';

export default function UpdatesSection() {
  const { status, setStatus } = useUpdateStatus();
  const [checking, setChecking] = useState(false);

  const onCheck = async () => {
    setChecking(true);
    try { setStatus(await checkForUpdates()); } catch { /* fail-silent */ }
    setChecking(false);
  };

  const onToggle = async (enabled) => {
    setStatus((s) => ({ ...(s || {}), auto_check_enabled: enabled }));
    try { await setUpdateAutoCheck(enabled); } catch { /* fail-silent */ }
  };

  const current = status?.current ?? '—';
  const available = status?.update_available;
  const auto = status?.auto_check_enabled ?? true;

  return (
    <section className="panel settings-section">
      <div className="panel-header">
        <SectionLabel marker="▶">Updates</SectionLabel>
      </div>

      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Version</span>
          <span className="settings-description">
            {available
              ? `Update available: ${current} → ${status.latest}${status.is_security ? ' (security)' : ''}`
              : `You're on the latest version (${current})`}
          </span>
        </div>
        <button type="button" className="settings-pill" onClick={onCheck} disabled={checking}>
          {checking ? 'checking…' : 'check now'}
        </button>
      </div>

      {available && (
        <div className="settings-row">
          <div className="settings-row-label">
            <span className="settings-label">Get the update</span>
            <span className="settings-description">
              {status.action_command ? status.action_command : 'Download the new build'}
            </span>
          </div>
          <button
            type="button"
            className="settings-pill"
            onClick={() => openExternal(status.latest_url || status.download_url)}
          >
            {status.action_command ? "what's new" : 'download'}
          </button>
        </div>
      )}

      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Automatic checks</span>
          <span className="settings-description">Check PyPI/GitHub for new versions once a day</span>
        </div>
        <div className="settings-pill-group">
          <button
            type="button"
            className={`settings-pill${auto ? ' settings-pill--active' : ''}`}
            onClick={() => onToggle(true)}
            aria-pressed={auto}
          >
            On
          </button>
          <button
            type="button"
            className={`settings-pill${!auto ? ' settings-pill--active' : ''}`}
            onClick={() => onToggle(false)}
            aria-pressed={!auto}
          >
            Off
          </button>
        </div>
      </div>
    </section>
  );
}
