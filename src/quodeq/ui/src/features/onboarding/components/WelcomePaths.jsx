import { t } from '../../../strings/index.js';

/**
 * The two ways in: score a repository, or connect an evaluations repository
 * (where evaluations are published, yours or your team's). The welcome panel
 * stacks them in its right column; the empty Repositories page lays them out
 * side by side with `compact`.
 *
 * Adapts to what already exists: with local projects the first card's action
 * reads "add another"; with an evaluations repository connected the second
 * card names it and goes to repositories instead of connecting. Importing one
 * exported archive is the rescue path of "existing evaluations", so it lives
 * on the second card as a link, shown only when `onImport` is wired.
 *
 * @param {object} props
 * @param {boolean} [props.compact]
 * @param {Function} props.onStart
 * @param {Function} props.onConnect
 * @param {Function} [props.onImport]
 * @param {Function} props.onGoToRepositories
 * @param {{ connected: boolean, host: string|null, hasLocalProjects: boolean }} props.adaptation
 */
export default function WelcomePaths({ compact = false, onStart, onConnect, onImport, onGoToRepositories, adaptation }) {
  const { connected = false, host = null, hasLocalProjects = false } = adaptation ?? {};
  return (
    <div className={`onboarding-paths__cards${compact ? ' onboarding-paths__cards--compact' : ''}`}>
      <RepoPathCard hasLocalProjects={hasLocalProjects} onStart={onStart} />
      <EvalsPathCard
        connected={connected}
        host={host}
        onConnect={onConnect}
        onImport={onImport}
        onGoToRepositories={onGoToRepositories}
      />
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

function EvalsPathCard({ connected, host, onConnect, onImport, onGoToRepositories }) {
  return (
    <article className="onboarding-path-card">
      <h3 className="onboarding-path-card__title">{t('onboarding.pathEvalsTitle')}</h3>
      <p className="onboarding-path-card__desc">{t('onboarding.pathEvalsDesc')}</p>
      {connected && (
        <p className="onboarding-path-card__status">
          <span className="onboarding-path-card__marker" aria-hidden="true">▸</span>
          <span>{t('onboarding.pathEvalsConnected', { host })}</span>
        </p>
      )}
      <div className="onboarding-path-card__actions">
        {connected ? (
          <button type="button" className="term-btn term-btn--secondary" onClick={onGoToRepositories}>
            {t('onboarding.pathEvalsGo')}
          </button>
        ) : (
          <button type="button" className="term-btn term-btn--secondary" onClick={onConnect}>
            {t('onboarding.pathEvalsConnect')}
          </button>
        )}
        {onImport && (
          <button type="button" className="onboarding-path-card__link" onClick={onImport}>
            {t('onboarding.pathEvalsImport')}
          </button>
        )}
      </div>
    </article>
  );
}
