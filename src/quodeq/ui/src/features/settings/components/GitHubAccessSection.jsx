import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import { useApi } from '../../../api/ApiContext.jsx';
import { t } from '../../../strings/index.js';
import { SettingsRowLabel } from './settingsRowParts.jsx';
import SignInCard from '../../github-access/components/SignInCard.jsx';
import { ACCOUNT_METHOD } from '../../github-access/accessVocab.js';
import { SignOutRow, TestAccessRow } from './githubAccessRows.jsx';

const QUERY_KEY = ['github', 'account'];
const MS_PER_S = 1000;

function statusText(account) {
  if (!account) return t('settings.checkingEllipsis');
  if (account.signedIn) {
    const expired = account.expiresAt != null && account.expiresAt * MS_PER_S <= Date.now();
    return t(expired ? 'settings.githubExpired' : 'settings.githubSignedInQuodeq', { login: account.login });
  }
  if (account.method === ACCOUNT_METHOD.GH) return t('settings.githubUsingGh');
  return t('settings.githubNotSignedIn');
}

export default function GitHubAccessSection() {
  const { getGithubAccount, signOutGithub, probeGit } = useApi();
  const { data: account, refetch } = useQuery({ queryKey: QUERY_KEY, queryFn: getGithubAccount });
  const [showSignIn, setShowSignIn] = useState(false);
  const [busy, setBusy] = useState(false);
  const notSignedIn = account != null && !account.signedIn;
  const canSignIn = notSignedIn && Boolean(account.signInAvailable);
  const signInMissing = notSignedIn && !account.signInAvailable && account.method !== ACCOUNT_METHOD.GH;

  async function signOut() {
    setBusy(true);
    try { await signOutGithub(); await refetch(); } finally { setBusy(false); }
  }

  return (
    <section className="panel settings-section">
      <div className="panel-header">
        <span className="settings-label-row"><SectionLabel marker="▶">{t('settings.githubAccessLabel')}</SectionLabel></span>
      </div>
      <div className="settings-row">
        <SettingsRowLabel hintSlot={false} label={t('settings.githubStatus')} description={statusText(account)} />
        {canSignIn && !showSignIn && (
          <button type="button" className="settings-pill" onClick={() => setShowSignIn(true)}>{t('settings.githubSignIn')}</button>
        )}
      </div>
      {signInMissing && <div className="settings-row"><p className="access-panel__hint">{t('githubAccess.signInUnavailable')}</p></div>}
      {showSignIn && canSignIn && (
        <div className="settings-row"><SignInCard onSignedIn={() => { setShowSignIn(false); refetch(); }} /></div>
      )}
      {account?.signedIn && <SignOutRow onSignOut={signOut} busy={busy} />}
      <TestAccessRow probeGit={probeGit} />
    </section>
  );
}
