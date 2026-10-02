import { t } from '../../../strings/index.js';
import { ACCESS_KIND } from '../accessVocab.js';

const HELP = {
  [ACCESS_KIND.HOST_KEY]: 'githubAccess.hostKeyHelp',
  [ACCESS_KIND.NETWORK]: 'githubAccess.networkHelp',
  [ACCESS_KIND.TIMEOUT]: 'githubAccess.networkHelp',
  [ACCESS_KIND.GIT_MISSING]: 'githubAccess.gitMissingHelp',
  [ACCESS_KIND.GIT_TOO_OLD]: 'githubAccess.gitTooOldHelp',
};

/** The raw git output, collapsed. */
export function Detail({ detail }) {
  if (!detail) return null;
  return (
    <details className="access-panel__detail">
      <summary>{t('githubAccess.detailLabel')}</summary>
      <pre><code>{detail}</code></pre>
    </details>
  );
}

function httpsFormOf(url) {
  return (url || '').replace(/^git@([^:]+):/, 'https://$1/').replace(/^ssh:\/\/(?:[^@]+@)?/, 'https://');
}

/** Kinds that sign-in cannot fix: say what to do, then offer try again. */
export function GuidanceOnly({ kind, host, url, cloneUrl, detail, onRetry }) {
  const help = HELP[kind];
  return (
    <>
      {help && <p className="access-panel__help">{t(help, { host })}</p>}
      {kind === ACCESS_KIND.HOST_KEY && <pre className="access-card__cmd"><code>{httpsFormOf(url)}</code></pre>}
      {kind === ACCESS_KIND.USE_HTTPS && cloneUrl && <pre className="access-card__cmd"><code>{cloneUrl}</code></pre>}
      <Detail detail={detail} />
      <button type="button" className="term-btn term-btn--primary term-btn--filled" onClick={onRetry}>{t('githubAccess.tryAgain')}</button>
    </>
  );
}
