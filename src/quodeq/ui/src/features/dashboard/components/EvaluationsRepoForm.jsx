import { useState } from 'react';
import { t } from '../../../strings/index.js';
import { TermInput } from '../../../components/terminal/index.js';
import AccessPanel from '../../github-access/components/AccessPanel.jsx';
import { FILE_URL_PREFIX } from '../../onboarding/onboardingVocab.js';
import { fileUrlFromPath } from '../../../utils/fileUrl.js';

// A scheme (https://, ssh://, file://), an scp-style git@host:path, or a
// user@host:path reads as a url; anything else typed is a path on this machine.
const URL_SHAPE = /^(?:[a-z][a-z0-9+.-]*:\/\/|git@|[\w.-]+@[\w.-]+:)/i;

// A local repository: a file url, or a path the user typed or picked.
function isLocal(value) {
  return value.startsWith(FILE_URL_PREFIX) || !URL_SHAPE.test(value);
}

// What goes to the server: a typed path travels as the file url it stands for.
function addressToSend(value) {
  return isLocal(value) && !value.startsWith(FILE_URL_PREFIX) ? fileUrlFromPath(value) : value;
}

// Under the field: the access panel when the probe refused the URL, else the
// mapped error (both retry the same URL).
function FormFeedback({ accessFailure, error, url, retry }) {
  if (accessFailure) {
    return (
      <div className="connect-team-card__access">
        <AccessPanel failure={accessFailure} url={url} onResolved={retry} onRetry={retry} />
      </div>
    );
  }
  return error ? <p className="inline-error evals-repo-form__error" role="alert">{error}</p> : null;
}

/**
 * Connect an evaluations repository: one field that takes a git url or a
 * local folder (typed as a path, or picked with `local folder`, which fills
 * the field), the same row as the add panel. A local folder is sent as a
 * `file://` url. Shared by the welcome's connect step and the Repositories
 * tab's failure card. Submitting only hands the address to `onConnect`; the
 * caller starts the job and feeds back `connecting`, `error` (display text)
 * and `accessFailure`.
 *
 * @param {object} props
 * @param {(url: string) => void} props.onConnect
 * @param {boolean} [props.connecting]
 * @param {string|null} [props.error]
 * @param {object|null} [props.accessFailure]
 * @param {string|null} [props.initialUrl] - a failed attempt's url, prefilled so connect retries it
 * @param {() => Promise<string|null>} [props.browseFolder] - picks a folder, resolves null when cancelled
 * @param {React.ReactNode} [props.secondaryAction] - the caller's back, cancel or close, at the left of connect
 */
export default function EvaluationsRepoForm({ onConnect, connecting = false, error = null, accessFailure = null, initialUrl = null, browseFolder, secondaryAction = null }) {
  const [url, setUrl] = useState(initialUrl ?? '');
  const trimmed = url.trim();
  const address = trimmed ? addressToSend(trimmed) : '';
  const submitNow = () => {
    if (address && !connecting) onConnect(address);
  };
  const pickFolder = async () => {
    const path = await browseFolder?.();
    if (path) setUrl(fileUrlFromPath(path));
  };
  return (
    <form className="evals-repo-form" onSubmit={(e) => { e.preventDefault(); submitNow(); }}>
      <div className="evals-repo-form__row">
        <span className="repo-form__field">
          <TermInput
            command="repo"
            value={url}
            onChange={setUrl}
            placeholder={t('projects.connectTeamPlaceholder')}
            ariaLabel={t('projects.connectTeamUrlAria')}
            disabled={connecting}
          />
        </span>
        {browseFolder && (
          <button type="button" className="term-btn term-btn--secondary" onClick={pickFolder} disabled={connecting}>
            {t('onboarding.localFolder')}
          </button>
        )}
      </div>
      {trimmed && isLocal(trimmed) && <p className="evals-repo-form__hint">{t('onboarding.folderBareHint')}</p>}
      <FormFeedback accessFailure={accessFailure} error={error} url={address} retry={() => onConnect(address)} />
      <div className="evals-repo-form__actions">
        {secondaryAction}
        <button type="submit" className="term-btn term-btn--primary term-btn--filled evals-repo-form__submit" disabled={connecting || !address}>
          {connecting ? t('projects.connectTeamConnecting') : t('projects.connectTeamButton')}
        </button>
      </div>
    </form>
  );
}
