import { useState } from 'react';
import { t } from '../../../strings/index.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';
import { SettingsRowLabel } from './settingsRowParts.jsx';
import { ACCESS_KIND } from '../../github-access/accessVocab.js';

export function SignOutRow({ onSignOut, busy }) {
  const [confirming, setConfirming] = useState(false);
  if (!confirming) {
    return (
      <div className="settings-row">
        <button type="button" className="settings-pill settings-pill--accent" onClick={() => setConfirming(true)} disabled={busy}>{t('settings.githubSignOut')}</button>
      </div>
    );
  }
  return (
    <div className="settings-row">
      <span className="settings-row-confirm-label">{t('settings.githubSignOutConfirm')}</span>
      <button type="button" className="settings-pill settings-pill--confirm" onClick={() => { setConfirming(false); onSignOut(); }} disabled={busy}>{t('settings.yes')}</button>
      <button type="button" className="settings-pill" onClick={() => setConfirming(false)} disabled={busy}>{t('settings.no')}</button>
    </div>
  );
}

export function TestAccessRow({ probeGit }) {
  const [url, setUrl] = useState('');
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  async function test() {
    setBusy(true);
    try {
      setResult(await probeGit(url.trim()));
    } catch (err) {
      setResult({ reachable: false, kind: ACCESS_KIND.UNKNOWN, detail: apiErrorMessage(err, 'apiError.accessUnknown') });
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="settings-row">
        <SettingsRowLabel hintSlot={false} label={t('settings.githubTestAccess')} description={t('settings.githubTestDesc')} />
      </div>
      <div className="settings-row settings-row--last">
        <input type="text" className="settings-input" placeholder={t('settings.githubTestPlaceholder')} value={url} onChange={(e) => setUrl(e.target.value)} aria-label={t('settings.githubTestAccess')} />
        <button type="button" className="settings-pill" onClick={test} disabled={busy || !url.trim()}>{busy ? t('githubAccess.testing') : t('settings.test')}</button>
      </div>
      {result && (
        <div className="settings-row settings-row--last">
          <p className={result.reachable ? 'access-card__ok' : 'inline-error'}>
            {result.reachable ? t('settings.githubTestReachable', { method: result.method }) : t('settings.githubTestBlocked', { kind: result.kind })}
          </p>
          {result.detail && <pre className="access-card__cmd"><code>{result.detail}</code></pre>}
        </div>
      )}
    </>
  );
}
