import { useState } from 'react';
import { TermHeader } from '../../../../components/terminal/index.js';

const STORAGE_KEY = 'quodeq.lastCloneRoot';

function readInitialDest() {
  try {
    if (typeof localStorage !== 'undefined') {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) return stored;
    }
  } catch {
    // ignore (private mode, disabled storage, etc.)
  }
  return '~';
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
      <TermHeader name="clone" sub={`step ${stepIndex} of ${stepTotal} · pick a clone destination`} />
      <p className="onboarding-step__pitch">Where should we clone this repo?</p>
      {repoUrl && <p className="onboarding-clone-target__repo-url"><code>{repoUrl}</code></p>}

      <form onSubmit={handleSubmit} className="onboarding-clone-target__form">
        <label htmlFor="clone-dest-input" className="onboarding-clone-target__label">Clone destination</label>
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
          The repo will be cloned into this folder. You manage it from here, like any local repo.
        </p>
        {error && <p className="onboarding-clone-target__error" role="alert">{error}</p>}

        <div className="onboarding-step__actions">
          <button
            type="submit"
            className="term-btn term-btn--primary term-btn--filled"
            disabled={submitting || !cloneDest.trim()}
          >
            {submitting ? 'cloning...' : 'clone and scan'}
          </button>
          <button
            type="button"
            className="term-btn term-btn--secondary"
            onClick={onBack}
            disabled={submitting}
          >
            back
          </button>
        </div>
      </form>

      <div className="onboarding-clone-target__escape-hatch">
        <button
          type="button"
          className="onboarding-edit-link"
          onClick={handleEphemeral}
          disabled={submitting}
        >
          Just run one evaluation, don't keep a copy
        </button>
      </div>
    </div>
  );
}
