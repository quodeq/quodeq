import { useId } from 'react';
import { t } from '../../../strings/index.js';
import EvaluationsRepoForm from './EvaluationsRepoForm.jsx';
import { useFolderPicker } from '../hooks/useFolderPicker.jsx';

/**
 * "▸ evaluations repository": the Repositories tab's card for a failed
 * connect (spec 4.1). The connect itself starts from the welcome's connect
 * step; when its job fails the failure comes back here, either as the access
 * panel (the probe refused the URL) or as the connect slot's mapped error
 * under the field, with the url-or-folder form prefilled so connect retries.
 *
 * Props come from useSharedProjects (the screen's one status poll):
 * `onConnect(url)`, `connecting`, `error` (display text), `accessFailure`,
 * and `initialUrl` (the URL of a failed connect, so pressing connect retries it).
 * `onClose`, when given, renders a "close" control (dismisses the card).
 */
export default function ConnectTeamCard({ onConnect, connecting = false, error = null, accessFailure = null, initialUrl = null, onClose = null }) {
  const titleId = useId();
  const { browseFolder, picker } = useFolderPicker();
  return (
    <section className="connect-team-card" aria-labelledby={titleId}>
      <div className="connect-team-card__head">
        <h3 className="connect-team-card__title" id={titleId}>
          <span className="connect-team-card__marker" aria-hidden="true">▸</span> {t('projects.connectTeamTitle')}
        </h3>
        {onClose && (
          <button type="button" className="connect-team-card__close" onClick={onClose} aria-label={t('projects.connectTeamClose')}>
            <span aria-hidden="true">×</span>
          </button>
        )}
      </div>
      <p className="connect-team-card__desc">{t('projects.connectTeamDesc')}</p>
      <EvaluationsRepoForm
        onConnect={(url) => onConnect?.(url)}
        connecting={connecting}
        error={error}
        accessFailure={accessFailure}
        initialUrl={initialUrl}
        browseFolder={browseFolder}
      />
      {picker}
    </section>
  );
}
