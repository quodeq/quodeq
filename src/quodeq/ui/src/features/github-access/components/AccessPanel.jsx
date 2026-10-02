import { useEffect, useState } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { t } from '../../../strings/index.js';
import { ACCESS_KIND, SIGN_IN_KINDS } from '../accessVocab.js';
import SignInCard from './SignInCard.jsx';
import GhCliCard from './GhCliCard.jsx';
import OtherWaysCards from './OtherWaysCards.jsx';
import { Detail, GuidanceOnly } from './AccessGuidance.jsx';

const HEADINGS = {
  [ACCESS_KIND.AUTH_REQUIRED]: 'githubAccess.headingAuth',
  [ACCESS_KIND.NOT_FOUND]: 'githubAccess.headingNotFound',
  [ACCESS_KIND.HOST_KEY]: 'githubAccess.headingHostKey',
  [ACCESS_KIND.NETWORK]: 'githubAccess.headingNetwork',
  [ACCESS_KIND.TIMEOUT]: 'githubAccess.headingNetwork',
  [ACCESS_KIND.GIT_MISSING]: 'githubAccess.headingGitMissing',
  [ACCESS_KIND.GIT_TOO_OLD]: 'githubAccess.headingGitTooOld',
  [ACCESS_KIND.UNKNOWN]: 'githubAccess.headingUnknown',
  [ACCESS_KIND.USE_HTTPS]: 'githubAccess.headingUseHttps',
};

function useAccount(getGithubAccount, enabled) {
  const [account, setAccount] = useState(null);
  useEffect(() => {
    if (!enabled) return undefined;
    let alive = true;
    getGithubAccount().then((a) => { if (alive) setAccount(a); }).catch((err) => { console.warn('[AccessPanel] account lookup failed:', err); });
    return () => { alive = false; };
  }, [getGithubAccount, enabled]);
  return account;
}

/**
 * Which GitHub rungs to offer. Nothing until the account answers: a build
 * without an OAuth client id must never offer a sign-in that can only fail.
 */
function rungsFor(account, isGitHub) {
  if (!isGitHub || account == null) return { showSignIn: false, showGhCard: false, showGhHint: false, signInMissing: false };
  return {
    showSignIn: Boolean(account.signInAvailable),
    showGhCard: Boolean(account.ghAvailable && !account.ghLoggedIn),
    showGhHint: !account.ghAvailable,
    signInMissing: !account.signInAvailable && !account.ghLoggedIn,
  };
}

function SignInRungs({ failure, url, onResolved, onTestAgain, testing, blocked }) {
  const { getGithubAccount } = useApi();
  const { kind, detail, isGitHub } = failure;
  const account = useAccount(getGithubAccount, isGitHub);
  const { showSignIn, showGhCard, showGhHint, signInMissing } = rungsFor(account, isGitHub);
  return (
    <>
      {kind === ACCESS_KIND.NOT_FOUND && isGitHub && <p className="access-panel__help">{t('githubAccess.privateHint')}</p>}
      <Detail detail={detail} />
      {showSignIn && <SignInCard onSignedIn={() => onResolved()} />}
      {showGhCard && <GhCliCard onCheckAgain={onTestAgain} checking={testing} />}
      {showGhHint && <p className="access-panel__hint">{t('githubAccess.ghInstallHint')}</p>}
      {signInMissing && <p className="access-panel__hint">{t('githubAccess.signInUnavailable')}</p>}
      <OtherWaysCards url={url} isGitHub={isGitHub} onTokenAccepted={() => onResolved()} onTestAgain={onTestAgain} testing={testing} blocked={blocked} defaultOpen={signInMissing} />
    </>
  );
}

/**
 * Rendered where a clone was refused: the honest reason, then the ways forward.
 * `failure` is the probe envelope {kind, detail, host, isGitHub}.
 */
export default function AccessPanel({ failure, url, onResolved, onRetry }) {
  const { probeGit } = useApi();
  const { kind, detail, host } = failure;
  const [testing, setTesting] = useState(false);
  const [blocked, setBlocked] = useState(false);

  async function testAgain() {
    setTesting(true); setBlocked(false);
    try {
      const result = await probeGit(url);
      if (result.reachable) onResolved(); else setBlocked(true);
    } catch (err) { console.warn('[AccessPanel] probe failed:', err); setBlocked(true); } finally { setTesting(false); }
  }

  const heading = t(HEADINGS[kind] || 'githubAccess.headingUnknown', { host });
  return (
    <div className="access-panel" role="region" aria-label={heading}>
      <p className="access-panel__heading">{heading}</p>
      {SIGN_IN_KINDS.includes(kind)
        ? <SignInRungs failure={failure} url={url} onResolved={onResolved} onTestAgain={testAgain} testing={testing} blocked={blocked} />
        : <GuidanceOnly kind={kind} host={host} url={url} cloneUrl={failure.cloneUrl} detail={detail} onRetry={onRetry} />}
    </div>
  );
}
