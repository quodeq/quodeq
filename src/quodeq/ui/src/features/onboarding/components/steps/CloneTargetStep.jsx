import { useState } from 'react';
import { TermHeader } from '../../../../components/terminal/index.js';
import { t } from '../../../../strings/index.js';
import { readString } from '../../../../adapters/storage.js';

const STORAGE_KEY = 'quodeq.lastCloneRoot';

function readInitialDest() {
  return readString(STORAGE_KEY) || '~';
}

function CloneTargetForm({ cloneDest, setCloneDest, submitting, error, handleSubmit, onBack }) {
  return (
    <form onSubmit={handleSubmit} className="onboarding-clone-target__form">
      <label htmlFor="clone-dest-input" className="onboarding-clone-target__label">{t('onboarding.cloneDestLabel')}</label>
      <input
        id="clone-dest-input"
        type="text"
        className="onboarding-clone-target__input"
        value={cloneDest}
        onChange={(e) => setCloneDest(e.target.value)}
        disabled={submitting}
        autoFocus
      />
      <p className="onboarding-clone-target__hint">
        {t('onboarding.cloneDestDesc')}
      </p>
      {error && <p className="onboarding-clone-target__error" role="alert">{error}</p>}

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
  stepIndex = 0,
  stepTotal = 0,
}) {
  const [cloneDest, setCloneDest] = useState(readInitialDest);

  function handleSubmit(e) {
    e.preventDefault();
    onSubmit({ cloneDest: cloneDest.trim(), ephemeral: false });
  }

  function handleEphemeral() {
    onSubmit({ cloneDest: null, ephemeral: true });
  }

  return (
    <div className="onboarding-step onboarding-step--clone-target">
      <TermHeader name={t('onboarding.termClone')} sub={t('onboarding.subClone', { step: stepIndex, total: stepTotal })} />
      <p className="onboarding-step__pitch">{t('onboarding.cloneWhere')}</p>
      {repoUrl && <p className="onboarding-clone-target__repo-url"><code>{repoUrl}</code></p>}

      <CloneTargetForm
        cloneDest={cloneDest} setCloneDest={setCloneDest} submitting={submitting} error={error}
        handleSubmit={handleSubmit} onBack={onBack}
      />

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
