import { useState } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { t } from '../../../strings/index.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';

const TOKEN_URL = 'https://github.com/settings/tokens/new?scopes=repo&description=quodeq';

export function sshFormOf(url) {
  // https://host/owner/repo(.git) -> git@host:owner/repo.git ; other forms pass through.
  const m = /^https:\/\/([^/]+)\/(.+?)(?:\.git)?\/?$/.exec(url || '');
  return m ? `git@${m[1]}:${m[2]}.git` : url;
}

function PasteTokenCard({ onTokenAccepted }) {
  const { pasteGithubToken } = useApi();
  const [token, setToken] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  async function submit() {
    setBusy(true); setError(null);
    try {
      const { login } = await pasteGithubToken(token.trim());
      onTokenAccepted(login);
    } catch (err) {
      setError(apiErrorMessage(err, 'apiError.tokenInvalid'));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="access-card">
      <h4 className="access-card__title">{t('githubAccess.pasteTitle')}</h4>
      <p className="access-card__desc">{t('githubAccess.pasteDesc')} <a href={TOKEN_URL} target="_blank" rel="noreferrer">{t('githubAccess.pasteLink')}</a></p>
      <div className="access-card__row">
        <input type="password" className="settings-input" placeholder={t('githubAccess.pastePlaceholder')} value={token} onChange={(e) => setToken(e.target.value)} aria-label={t('githubAccess.pasteTitle')} />
        <button type="button" className="term-btn term-btn--secondary" onClick={submit} disabled={busy || !token.trim()}>{t('githubAccess.connect')}</button>
      </div>
      {error && <p className="inline-error" role="alert">{error}</p>}
    </section>
  );
}

function OwnGitCard({ url, onTestAgain, testing, blocked }) {
  return (
    <section className="access-card">
      <h4 className="access-card__title">{t('githubAccess.ownGitTitle')}</h4>
      <p className="access-card__desc">{t('githubAccess.ownGitHttps')}</p>
      <p className="access-card__desc">{t('githubAccess.ownGitSsh')}</p>
      <pre className="access-card__cmd"><code>{sshFormOf(url)}</code></pre>
      <button type="button" className="term-btn term-btn--secondary" onClick={onTestAgain} disabled={testing}>
        {testing ? t('githubAccess.testing') : t('githubAccess.testAgain')}
      </button>
      {blocked && <p className="inline-error" role="alert">{t('githubAccess.stillBlocked')}</p>}
    </section>
  );
}

/**
 * The collapsed "other ways" group, or the own-git card alone for non-GitHub hosts.
 * `defaultOpen` expands it until the user toggles it (no sign-in card above it).
 */
export default function OtherWaysCards({ url, isGitHub, onTokenAccepted, onTestAgain, testing, blocked, defaultOpen = false }) {
  const [toggled, setToggled] = useState(null);
  const open = toggled ?? defaultOpen;
  if (!isGitHub) return <OwnGitCard url={url} onTestAgain={onTestAgain} testing={testing} blocked={blocked} />;
  return (
    <div className="access-other-ways">
      <button type="button" className="onboarding-edit-link" aria-expanded={open} onClick={() => setToggled(!open)}>{t('githubAccess.otherWays')}</button>
      {open && (
        <>
          <PasteTokenCard onTokenAccepted={onTokenAccepted} />
          <OwnGitCard url={url} onTestAgain={onTestAgain} testing={testing} blocked={blocked} />
        </>
      )}
    </div>
  );
}
