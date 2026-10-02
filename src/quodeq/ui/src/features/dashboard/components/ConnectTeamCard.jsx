import { useId, useState } from 'react';
import { t } from '../../../strings/index.js';
import AccessPanel from '../../github-access/components/AccessPanel.jsx';

/**
 * "▸ team results": the Repositories tab's inline form for connecting the
 * team's results repository (spec 4.1). Submitting only starts the connect
 * job; its progress shows in the sync strip and a failure comes back here,
 * either as the access panel (the probe refused the URL) or as the connect
 * slot's mapped error under the field.
 *
 * Props come from useSharedProjects (the screen's one status poll):
 * `onConnect(url)`, `connecting`, `error` (display text), `accessFailure`.
 */
export default function ConnectTeamCard({ onConnect, connecting = false, error = null, accessFailure = null }) {
  const [url, setUrl] = useState('');
  const titleId = useId();
  const trimmed = url.trim();
  const submit = () => {
    if (!trimmed || connecting) return;
    onConnect?.(trimmed);
  };
  return (
    <section className="connect-team-card" aria-labelledby={titleId}>
      <h3 className="connect-team-card__title" id={titleId}>
        <span className="connect-team-card__marker" aria-hidden="true">▸</span> {t('projects.connectTeamTitle')}
      </h3>
      <p className="connect-team-card__desc">{t('projects.connectTeamDesc')}</p>
      <form
        className="connect-team-card__row"
        onSubmit={(e) => { e.preventDefault(); submit(); }}
      >
        <input
          type="text"
          className="connect-team-card__input"
          placeholder={t('projects.connectTeamPlaceholder')}
          aria-label={t('projects.connectTeamUrlAria')}
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          disabled={connecting}
          spellCheck={false}
          autoComplete="off"
        />
        <button type="submit" className="term-btn term-btn--primary term-btn--filled connect-team-card__btn" disabled={connecting}>
          {connecting ? t('projects.connectTeamConnecting') : t('projects.connectTeamButton')}
        </button>
      </form>
      {accessFailure ? (
        <div className="connect-team-card__access">
          <AccessPanel failure={accessFailure} url={trimmed} onResolved={submit} onRetry={submit} />
        </div>
      ) : (
        error && <p className="inline-error connect-team-card__error" role="alert">{error}</p>
      )}
    </section>
  );
}
