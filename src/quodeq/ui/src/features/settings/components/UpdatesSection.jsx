import { useState } from 'react';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import { useApi } from '../../../api/ApiContext.jsx';
import { useUpdateStatus } from '../../updates/useUpdateStatus.js';
import { useSelfUpdate } from '../../updates/useSelfUpdate.js';
import { openExternal } from '../../updates/openExternal.js';
import { t } from '../../../strings/index.js';

function VersionRow({ available, status, current, checking, onCheck }) {
  return (
    <div className="settings-row">
      <div className="settings-row-label">
        <span className="settings-label">{t('settings.versionLabel')}</span>
        <span className="settings-description">
          {available
            ? (status.is_security
                ? t('settings.updateAvailableSecurity', { current, latest: status.latest })
                : t('settings.updateAvailable', { current, latest: status.latest }))
            : t('settings.upToDate', { version: current })}
        </span>
      </div>
      <button type="button" className="settings-pill" onClick={onCheck} disabled={checking}>
        {checking ? t('settings.checking') : t('settings.checkNow')}
      </button>
    </div>
  );
}

const PHASE_STRINGS = {
  downloading: 'updates.downloading',
  verifying: 'updates.verifying',
  installing: 'updates.installing',
  relaunching: 'updates.relaunching',
};

function UpdateAvailableRow({ status, selfUpdate }) {
  const description = selfUpdate.active
    ? t(PHASE_STRINGS[selfUpdate.phase], { percent: selfUpdate.percent })
    : selfUpdate.failed
      ? t('updates.selfUpdateFailed', { version: status.latest })
      : status.action_command
        ? status.action_command
        : t('settings.downloadNewBuild');
  return (
    <div className="settings-row">
      <div className="settings-row-label">
        <span className="settings-label">{t('settings.getTheUpdate')}</span>
        <span className="settings-description">{description}</span>
      </div>
      {selfUpdate.supported && !selfUpdate.failed ? (
        <button
          type="button"
          className="settings-pill"
          disabled={selfUpdate.active || selfUpdate.starting}
          onClick={selfUpdate.begin}
        >
          {t('updates.updateAndRelaunch')}
        </button>
      ) : (
        <button
          type="button"
          className="settings-pill"
          onClick={() => openExternal(status.latest_url || status.download_url)}
        >
          {status.action_command ? t('settings.whatsNew') : t('settings.download')}
        </button>
      )}
    </div>
  );
}

function AutoCheckRow({ auto, onToggle }) {
  return (
    <div className="settings-row">
      <div className="settings-row-label">
        <span className="settings-label">{t('settings.automaticChecks')}</span>
        <span className="settings-description">{t('settings.automaticChecksDesc')}</span>
      </div>
      <div className="settings-pill-group">
        <button
          type="button"
          className={`settings-pill${auto ? ' settings-pill--active' : ''}`}
          onClick={() => onToggle(true)}
          aria-pressed={auto}
        >
          {t('settings.on')}
        </button>
        <button
          type="button"
          className={`settings-pill${!auto ? ' settings-pill--active' : ''}`}
          onClick={() => onToggle(false)}
          aria-pressed={!auto}
        >
          {t('settings.off')}
        </button>
      </div>
    </div>
  );
}

export default function UpdatesSection() {
  const { checkForUpdates, setUpdateAutoCheck } = useApi();
  const { status, setStatus } = useUpdateStatus();
  const selfUpdate = useSelfUpdate(status, setStatus);
  const [checking, setChecking] = useState(false);

  const onCheck = async () => {
    setChecking(true);
    try { setStatus(await checkForUpdates()); } catch { /* fail-silent */ }
    setChecking(false);
  };

  const onToggle = async (enabled) => {
    const previous = status?.auto_check_enabled;
    setStatus((s) => ({ ...(s || {}), auto_check_enabled: enabled }));
    try {
      await setUpdateAutoCheck(enabled);
    } catch {
      setStatus((s) => ({ ...(s || {}), auto_check_enabled: previous }));
    }
  };

  const current = status?.current ?? '—';
  const available = status?.update_available;
  const auto = status?.auto_check_enabled ?? true;

  return (
    <section className="panel settings-section">
      <div className="panel-header">
        <SectionLabel marker="▶">{t('settings.updatesLabel')}</SectionLabel>
      </div>

      <VersionRow available={available} status={status} current={current} checking={checking} onCheck={onCheck} />

      {available && <UpdateAvailableRow status={status} selfUpdate={selfUpdate} />}

      <AutoCheckRow auto={auto} onToggle={onToggle} />
    </section>
  );
}
