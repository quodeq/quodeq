import { useState } from 'react';
import { t } from '../../../strings/index.js';
import { TermInput } from '../../../components/terminal/index.js';
import AccessPanel from '../../github-access/components/AccessPanel.jsx';
import RepoSourceSwitch from '../../onboarding/components/analyze/RepoSourceSwitch.jsx';
import FolderField from '../../onboarding/components/analyze/FolderField.jsx';
import { REPO_SOURCE, FILE_URL_PREFIX } from '../../onboarding/onboardingVocab.js';
import { fileUrlFromPath, pathFromFileUrl } from '../../../utils/fileUrl.js';

function sourceOf(url) {
  return url?.startsWith(FILE_URL_PREFIX) ? REPO_SOURCE.FOLDER : REPO_SOURCE.URL;
}

function UrlField({ url, setUrl, connecting }) {
  return (
    <span className="repo-form__field">
      <TermInput
        value={url}
        onChange={setUrl}
        placeholder={t('projects.connectTeamPlaceholder')}
        ariaLabel={t('projects.connectTeamUrlAria')}
        disabled={connecting}
      />
    </span>
  );
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
 * Connect an evaluations repository by a pasted git url or a local folder
 * (sent as a `file://` url). Shared by the welcome's connect step and the
 * Repositories tab's failure card. Submitting only hands the url to
 * `onConnect`; the caller starts the job and feeds back `connecting`,
 * `error` (display text) and `accessFailure`.
 *
 * @param {object} props
 * @param {(url: string) => void} props.onConnect
 * @param {boolean} [props.connecting]
 * @param {string|null} [props.error]
 * @param {object|null} [props.accessFailure]
 * @param {string|null} [props.initialUrl] - a failed attempt's url; a file url opens on the folder source
 * @param {() => Promise<string|null>} [props.browseFolder] - picks a folder, resolves null when cancelled
 */
export default function EvaluationsRepoForm({ onConnect, connecting = false, error = null, accessFailure = null, initialUrl = null, browseFolder }) {
  const [source, setSource] = useState(() => sourceOf(initialUrl));
  const [url, setUrl] = useState(initialUrl ?? '');
  const trimmed = url.trim();
  const folderPath = pathFromFileUrl(url);
  const submitNow = () => {
    if (trimmed && !connecting) onConnect(trimmed);
  };
  const pickFolder = async () => {
    const path = await browseFolder?.();
    if (path) setUrl(fileUrlFromPath(path));
  };
  const switchSource = (next) => {
    if (next === source) return;
    setSource(next);
    setUrl('');
  };
  return (
    <form className="evals-repo-form" onSubmit={(e) => { e.preventDefault(); submitNow(); }}>
      <RepoSourceSwitch value={source} onChange={switchSource} />
      <div className="evals-repo-form__row">
        {source === REPO_SOURCE.URL
          ? <UrlField url={url} setUrl={setUrl} connecting={connecting} />
          : <FolderField folderPath={folderPath} onPick={pickFolder} disabled={connecting} />}
        <button type="submit" className="term-btn term-btn--primary term-btn--filled evals-repo-form__submit" disabled={connecting || !trimmed}>
          {connecting ? t('projects.connectTeamConnecting') : t('projects.connectTeamButton')}
        </button>
      </div>
      {source === REPO_SOURCE.FOLDER && <p className="evals-repo-form__hint">{t('onboarding.folderBareHint')}</p>}
      <FormFeedback accessFailure={accessFailure} error={error} url={trimmed} retry={() => onConnect(trimmed)} />
    </form>
  );
}
