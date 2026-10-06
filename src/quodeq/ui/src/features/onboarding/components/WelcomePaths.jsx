import { t } from '../../../strings/index.js';
import '../../../styles/onboarding-welcome.css';

/**
 * The three ways in: add a repository to evaluate, connect an evaluations
 * repository (where evaluations are published, yours or your team's), or
 * import an archive another machine exported. The welcome panel stacks them
 * in its right column.
 *
 * Adapts to what already exists: with local projects the first card's action
 * reads "add another"; with an evaluations repository connected the second
 * card names it and offers `disconnect` instead of `connect` (the card stays
 * live either way, so a disconnect flips it back to connect in place). The
 * third card renders only when `onImport` is wired.
 *
 * @param {object} props
 * @param {Function} props.onStart
 * @param {Function} props.onConnect
 * @param {Function} [props.onDisconnect]
 * @param {Function} [props.onImport]
 * @param {{ connected: boolean, host: string|null, hasLocalProjects: boolean }} props.adaptation
 */
export default function WelcomePaths({ onStart, onConnect, onDisconnect, onImport, adaptation }) {
  const { connected = false, host = null, hasLocalProjects = false } = adaptation ?? {};
  return (
    <div className="onboarding-paths__cards">
      <RepoPathCard hasLocalProjects={hasLocalProjects} onStart={onStart} />
      <EvalsPathCard connected={connected} host={host} onConnect={onConnect} onDisconnect={onDisconnect} />
      {onImport && <ArchivePathCard onImport={onImport} />}
    </div>
  );
}

function RepoPathCard({ hasLocalProjects, onStart }) {
  return (
    <article className="onboarding-path-card onboarding-path-card--primary">
      <h3 className="onboarding-path-card__title">{t('onboarding.pathRepoTitle')}</h3>
      <p className="onboarding-path-card__desc">{t('onboarding.pathRepoDesc')}</p>
      <div className="onboarding-path-card__actions">
        <button type="button" className="term-btn term-btn--primary term-btn--filled" onClick={onStart}>
          {hasLocalProjects ? t('onboarding.pathRepoAddAnother') : t('onboarding.pathRepoStart')}
        </button>
      </div>
    </article>
  );
}

function EvalsPathCard({ connected, host, onConnect, onDisconnect }) {
  return (
    <article className="onboarding-path-card">
      <h3 className="onboarding-path-card__title">{t('onboarding.pathEvalsTitle')}</h3>
      <p className="onboarding-path-card__desc">{t('onboarding.pathEvalsDesc')}</p>
      {connected && (
        <p className="onboarding-path-card__status">
          <span className="onboarding-path-card__marker" aria-hidden="true">▸</span>
          <span>{host ? t('onboarding.pathEvalsConnected', { host }) : t('onboarding.pathEvalsConnectedBare')}</span>
        </p>
      )}
      <div className="onboarding-path-card__actions">
        {connected ? (
          onDisconnect && (
            <button type="button" className="term-btn term-btn--secondary" onClick={onDisconnect}>
              {t('onboarding.pathEvalsDisconnect')}
            </button>
          )
        ) : (
          <button type="button" className="term-btn term-btn--secondary" onClick={onConnect}>
            {t('onboarding.pathEvalsConnect')}
          </button>
        )}
      </div>
    </article>
  );
}

function ArchivePathCard({ onImport }) {
  return (
    <article className="onboarding-path-card">
      <h3 className="onboarding-path-card__title">{t('onboarding.pathArchiveTitle')}</h3>
      <p className="onboarding-path-card__desc">{t('onboarding.pathArchiveDesc')}</p>
      <div className="onboarding-path-card__actions">
        <button type="button" className="term-btn term-btn--secondary" onClick={onImport}>
          {t('onboarding.pathArchiveImport')}
        </button>
      </div>
    </article>
  );
}
