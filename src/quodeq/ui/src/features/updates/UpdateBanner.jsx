import { useState, useEffect } from 'react';
import { dismissUpdate, markUpdateDisclosed } from '../../api/index.js';
import { t } from '../../strings/index.js';
import { useUpdateStatus } from './useUpdateStatus.js';
import { useSelfUpdate } from './useSelfUpdate.js';
import { openExternal } from './openExternal.js';

const PHASE_STRINGS = {
  downloading: 'updates.downloading',
  verifying: 'updates.verifying',
  installing: 'updates.installing',
  relaunching: 'updates.relaunching',
};

// Both update-state writes are best-effort: the banner still behaves
// correctly if one fails, so the failure is logged rather than surfaced.
function warnPersistFailed(e) {
  console.warn('update-state persist failed:', e);
}

function ProgressBanner({ selfUpdate }) {
  return (
    <div className="update-banner" role="status">
      <span className="update-banner-text">
        {t(PHASE_STRINGS[selfUpdate.phase], { percent: selfUpdate.percent })}
      </span>
    </div>
  );
}

function BannerText({ status, selfUpdate }) {
  return (
    <span className="update-banner-text">
      {status.is_security ? <strong>{t('updates.securityPrefix')}</strong> : null}
      {selfUpdate.failed
        ? t('updates.selfUpdateFailed', { version: status.latest })
        : t('updates.available', { version: status.latest })}
      {status.action_command ? (
        <> {t('updates.runPrefix')} <code className="update-banner-cmd">{status.action_command}</code></>
      ) : null}
    </span>
  );
}

function UpdateAction({ status, selfUpdate }) {
  if (selfUpdate.supported && !selfUpdate.failed) {
    return (
      <button type="button" className="settings-pill" disabled={selfUpdate.starting} onClick={selfUpdate.begin}>
        {t('updates.updateAndRelaunch')}
      </button>
    );
  }
  return (
    <button type="button" className="settings-pill" onClick={() => openExternal(status.latest_url || status.download_url)}>
      {status.action_command ? t('updates.whatsNew') : t('updates.download')}
    </button>
  );
}

export default function UpdateBanner() {
  const { status, adopt } = useUpdateStatus();
  const selfUpdate = useSelfUpdate(status, adopt);
  const [dismissed, setDismissed] = useState(false);

  // First-run disclosure: record that the user has been informed.
  useEffect(() => {
    if (status && status.disclosed === false) {
      markUpdateDisclosed().catch(warnPersistFailed);
    }
  }, [status]);

  if (!status || !status.update_available || dismissed) return null;
  if (selfUpdate.active) return <ProgressBanner selfUpdate={selfUpdate} />;

  const onDismiss = () => {
    setDismissed(true);
    // Optimistic dismiss: the banner simply reappears next launch if the
    // request failed, but log the failure so it is diagnosable.
    dismissUpdate(status.latest).catch(warnPersistFailed);
  };

  return (
    <div className={`update-banner${status.is_security ? ' update-banner--security' : ''}`} role="status">
      <BannerText status={status} selfUpdate={selfUpdate} />
      <span className="update-banner-actions">
        <UpdateAction status={status} selfUpdate={selfUpdate} />
        <button type="button" className="update-banner-dismiss" aria-label={t('updates.dismissAria')} onClick={onDismiss}>
          ×
        </button>
      </span>
    </div>
  );
}
