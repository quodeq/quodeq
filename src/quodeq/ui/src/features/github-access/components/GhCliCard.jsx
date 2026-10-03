import { t } from '../../../strings/index.js';

/** Rung 3 as a card: only rendered when gh is installed but logged out. */
export default function GhCliCard({ onCheckAgain, checking }) {
  return (
    <section className="access-card">
      <h4 className="access-card__title">{t('githubAccess.ghTitle')}</h4>
      <p className="access-card__desc">{t('githubAccess.ghLoggedOut')}</p>
      <pre className="access-card__cmd"><code>{t('githubAccess.ghCommand')}</code></pre>
      <button type="button" className="term-btn term-btn--secondary" onClick={onCheckAgain} disabled={checking}>
        {checking ? t('githubAccess.testing') : t('githubAccess.checkAgain')}
      </button>
    </section>
  );
}
