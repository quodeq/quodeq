import { useState, useEffect } from 'react';
import { dismissUpdate, markUpdateDisclosed } from '../../api/index.js';
import { useUpdateStatus } from './useUpdateStatus.js';
import { openExternal } from './openExternal.js';

export default function UpdateBanner() {
  const { status } = useUpdateStatus();
  const [dismissed, setDismissed] = useState(false);

  // First-run disclosure: record that the user has been informed.
  useEffect(() => {
    if (status && status.disclosed === false) {
      markUpdateDisclosed().catch(() => {});
    }
  }, [status]);

  if (!status || !status.update_available || dismissed) return null;

  const onDismiss = () => {
    setDismissed(true);
    dismissUpdate(status.latest).catch(() => {});
  };

  return (
    <div className={`update-banner${status.is_security ? ' update-banner--security' : ''}`} role="status">
      <span className="update-banner-text">
        {status.is_security ? <strong>Security update: </strong> : null}
        Quodeq {status.current} → {status.latest} is available.
        {status.action_command ? (
          <> Run <code className="update-banner-cmd">{status.action_command}</code></>
        ) : null}
      </span>
      <span className="update-banner-actions">
        <button type="button" className="settings-pill" onClick={() => openExternal(status.latest_url || status.download_url)}>
          {status.action_command ? "what's new" : 'download'}
        </button>
        <button type="button" className="update-banner-dismiss" aria-label="Dismiss update notice" onClick={onDismiss}>
          ×
        </button>
      </span>
    </div>
  );
}
