import { useState } from 'react';
import { TermHeader } from '../../../../components/terminal/index.js';
import FolderBrowser from '../../../evaluation/components/FolderBrowser.jsx';
import { t } from '../../../../strings/index.js';
import { readString } from '../../../../adapters/storage.js';
import { LAST_CLONE_ROOT_STORAGE_KEY } from '../../../../constants.js';
import AccessPanel from '../../../github-access/components/AccessPanel.jsx';

// Where working copies go unless the user picks another folder. The server
// expands the tilde and creates the folder on first use.
export const DEFAULT_CLONE_ROOT = '~/quodeq/repos';

function readInitialDest() {
  return readString(LAST_CLONE_ROOT_STORAGE_KEY) || DEFAULT_CLONE_ROOT;
}

function CloneTargetForm({ cloneDest, setCloneDest, submitting, error, detail, accessFailure, handleSubmit, onBack, onBrowse }) {
  return (
    <form onSubmit={handleSubmit} className="onboarding-clone-target__form">
      <label htmlFor="clone-dest-input" className="onboarding-clone-target__label">{t('onboarding.cloneDestLabel')}</label>
      <div className="onboarding-repo-row">
        <input
          id="clone-dest-input"
          type="text"
          className="onboarding-clone-target__input"
          value={cloneDest}
          onChange={(e) => setCloneDest(e.target.value)}
          disabled={submitting}
          autoFocus
        />
        <button
          type="button"
          className="term-btn--secondary onboarding-repo-row__browse"
          onClick={onBrowse}
          disabled={submitting}
        >
          {t('onboarding.chooseCloneFolder')}
        </button>
      </div>
      <p className="onboarding-clone-target__hint">
        {t('onboarding.cloneDestDesc')}
      </p>
      {!accessFailure && error && (
        <div className="onboarding-clone-target__error" role="alert">
          <p>{error}</p>
          {detail && <pre className="access-card__cmd"><code>{detail}</code></pre>}
        </div>
      )}

      <div className="onboarding-step__actions">
        <button
          type="submit"
          className="term-btn term-btn--primary term-btn--filled"
          disabled={submitting || !cloneDest.trim()}
        >
          {submitting ? t('onboarding.cloning') : t('onboarding.cloneAndScan')}
        </button>
        <button
          type="button"
          className="term-btn term-btn--secondary"
          onClick={onBack}
          disabled={submitting}
        >
          {t('common.back')}
        </button>
      </div>
    </form>
  );
}

export default function CloneTargetStep({
  repoUrl,
  onSubmit,
  onBack,
  submitting = false,
  error = null,
  detail = '',
  accessFailure = null,
  onAccessResolved,
  onRetry,
  stepIndex = 0,
  stepTotal = 0,
}) {
  const [cloneDest, setCloneDest] = useState(readInitialDest);
  const [browserOpen, setBrowserOpen] = useState(false);

  function handleSubmit(e) {
    e.preventDefault();
    onSubmit({ cloneDest: cloneDest.trim(), ephemeral: false });
  }

  function handleEphemeral() {
    onSubmit({ cloneDest: null, ephemeral: true });
  }

  function handleFolderSelect(path) {
    setCloneDest(path);
    setBrowserOpen(false);
  }

  return (
    <div className="onboarding-step onboarding-step--clone-target">
      <TermHeader name={t('onboarding.termClone')} sub={t('onboarding.subClone', { step: stepIndex, total: stepTotal })} />
      <p className="onboarding-step__pitch">{t('onboarding.cloneWhere')}</p>
      {repoUrl && <p className="onboarding-clone-target__repo-url"><code>{repoUrl}</code></p>}

      <CloneTargetForm
        cloneDest={cloneDest} setCloneDest={setCloneDest} submitting={submitting} error={error}
        detail={detail} accessFailure={accessFailure}
        handleSubmit={handleSubmit} onBack={onBack} onBrowse={() => setBrowserOpen(true)}
      />
      {browserOpen && (
        <FolderBrowser
          onSelect={handleFolderSelect}
          onClose={() => setBrowserOpen(false)}
          title={t('onboarding.cloneDestLabel')}
          confirmText={t('onboarding.useThisFolder')}
        />
      )}
      {accessFailure && (
        <AccessPanel failure={accessFailure} url={repoUrl} onResolved={onAccessResolved} onRetry={onRetry} />
      )}

      <div className="onboarding-clone-target__escape-hatch">
        <button
          type="button"
          className="onboarding-edit-link"
          onClick={handleEphemeral}
          disabled={submitting}
        >
          {t('onboarding.ephemeral')}
        </button>
      </div>
    </div>
  );
}
