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

export default function UpdateBanner() {
  const { status, setStatus } = useUpdateStatus();
  const selfUpdate = useSelfUpdate(status, setStatus);
  const [dismissed, setDismissed] = useState(false);

  // First-run disclosure: record that the user has been informed.
  useEffect(() => {
    if (status && status.disclosed === false) {
      markUpdateDisclosed().catch((e) => console.warn('update-state persist failed:', e));
    }
  }, [status]);

  if (!status || !status.update_available || dismissed) return null;

  const onDismiss = () => {
    setDismissed(true);
    // Optimistic dismiss: the banner simply reappears next launch if the
    // request failed, but log the failure so it is diagnosable.
    dismissUpdate(status.latest).catch((e) => console.warn('update-state persist failed:', e));
  };

  if (selfUpdate.active) {
    return (
      <div className="update-banner" role="status">
        <span className="update-banner-text">
          {t(PHASE_STRINGS[selfUpdate.phase], { percent: selfUpdate.percent })}
        </span>
      </div>
    );
  }

  return (
    <div className={`update-banner${status.is_security ? ' update-banner--security' : ''}`} role="status">
      <span className="update-banner-text">
        {status.is_security ? <strong>{t('updates.securityPrefix')}</strong> : null}
        {selfUpdate.failed
          ? t('updates.selfUpdateFailed', { version: status.latest })
          : t('updates.available', { version: status.latest })}
        {status.action_command ? (
          <> {t('updates.runPrefix')} <code className="update-banner-cmd">{status.action_command}</code></>
        ) : null}
      </span>
      <span className="update-banner-actions">
        {selfUpdate.supported && !selfUpdate.failed ? (
          <button
            type="button"
            className="settings-pill"
            disabled={selfUpdate.starting}
            onClick={selfUpdate.begin}
          >
            {t('updates.updateAndRelaunch')}
          </button>
        ) : (
          <button type="button" className="settings-pill" onClick={() => openExternal(status.latest_url || status.download_url)}>
            {status.action_command ? t('updates.whatsNew') : t('updates.download')}
          </button>
        )}
        <button type="button" className="update-banner-dismiss" aria-label={t('updates.dismissAria')} onClick={onDismiss}>
          ×
        </button>
      </span>
    </div>
  );
}
