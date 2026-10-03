import { useEffect, useState } from 'react';
import { useWizardState } from '../hooks/useWizardState.js';
import { useOnboardingEffects } from '../hooks/useOnboardingEffects.js';
import { useOnboardingWizardHandlers } from '../hooks/useOnboardingWizardHandlers.js';
import { STEP_WELCOME, SETUP_ORDER } from '../wizardSteps.js';
import { WIZARD_SOURCE } from '../onboardingVocab.js';
import { OnboardingStepSwitch } from './OnboardingStepSwitch.jsx';
import { t } from '../../../strings/index.js';
import '../../../styles/onboarding.css';

export default function OnboardingWizard({ entry, onClose, onLaunch, onGoToRepositories, onStepChange }) {
  const initialStep = entry.startStep || STEP_WELCOME;
  const wizard = useWizardState({ initial: { step: initialStep, isFirstProject: entry.isFirstProject ?? true } });
  const [standards, setStandards] = useState([]);

  useOnboardingEffects({ wizard, entry, setStandards });
  // Reports the live step to the lifecycle, which only lets shared content
  // close a wizard that is still on its welcome step. Keyed on the step
  // alone: the callback's identity changes every render and need not re-fire.
  useEffect(() => { onStepChange?.(wizard.state.step); }, [wizard.state.step]);

  // The "step N of M" counter of the resume-setup walk (the only steps that show one).
  const currentIndex = SETUP_ORDER.indexOf(wizard.state.step) + 1;

  const {
    handleSkipWelcome, handleImport, handleClose, handleLaunch, nextStep, prevStep,
  } = useOnboardingWizardHandlers({
    wizard, onClose, onLaunch, onGoToRepositories, fromSettings: entry.source === WIZARD_SOURCE.SETTINGS,
  });
  // The welcome's two columns need a wider frame than the single-column steps.
  const frameClass = wizard.state.step === STEP_WELCOME
    ? 'onboarding-wizard__panel-frame onboarding-wizard__panel-frame--wide'
    : 'onboarding-wizard__panel-frame';

  return (
    <div className="onboarding-wizard" role="dialog" aria-modal="true" aria-label={t('onboarding.dialogAria')}>
      <div className={frameClass}>
        <button type="button" className="onboarding-wizard__close" aria-label={t('onboarding.close')} onClick={handleClose}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>

        <OnboardingStepSwitch
          wizard={wizard}
          entry={entry}
          standards={standards}
          currentIndex={currentIndex}
          visibleCount={SETUP_ORDER.length}
          nextStep={nextStep}
          prevStep={prevStep}
          handleSkipWelcome={handleSkipWelcome}
          handleImport={handleImport}
          handleLaunch={handleLaunch}
          handleClose={handleClose}
          onGoToRepositories={onGoToRepositories}
        />
      </div>
    </div>
  );
}
