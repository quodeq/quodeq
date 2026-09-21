import { useMemo, useState } from 'react';
import { registerProject, getProjectInfo } from '../../../api/index.js';
import { useWizardState } from '../hooks/useWizardState.js';
import { useOnboardingEffects } from '../hooks/useOnboardingEffects.js';
import { useOnboardingWizardHandlers } from '../hooks/useOnboardingWizardHandlers.js';
import { STEP_WELCOME, STEP_REPO_SCAN, STEP_PROVIDER, STEP_STANDARD_LAUNCH } from '../wizardSteps.js';
import { OnboardingStepSwitch } from './OnboardingStepSwitch.jsx';
import { t } from '../../../strings/index.js';
import '../../../styles/onboarding.css';

// The steps the "step N of M" counter counts. Welcome is excluded, and the
// provider step only appears while no provider is configured.
function visibleSteps(providerConfigured) {
  const seen = [STEP_REPO_SCAN];
  if (!providerConfigured) seen.push(STEP_PROVIDER);
  seen.push(STEP_STANDARD_LAUNCH);
  return seen;
}

export default function OnboardingWizard({ entry, onClose, onLaunch }) {
  const initialStep = entry.startStep || STEP_WELCOME;
  const wizard = useWizardState({ initial: { step: initialStep, isFirstProject: entry.isFirstProject ?? true } });
  const [standards, setStandards] = useState([]);

  useOnboardingEffects({ wizard, entry, setStandards });

  const providerConfigured = Boolean(wizard.state.provider.id && wizard.state.provider.model);
  const visible = useMemo(() => visibleSteps(providerConfigured), [providerConfigured]);
  const currentIndex = visible.indexOf(wizard.state.step) + 1;

  const {
    handleSkipWelcome, handleClose, handleLaunch, nextStep, prevStep,
  } = useOnboardingWizardHandlers({ wizard, onClose, onLaunch, providerConfigured });

  return (
    <div className="onboarding-wizard" role="dialog" aria-modal="true" aria-label={t('onboarding.dialogAria')}>
      <div className="onboarding-wizard__panel-frame">
        <button type="button" className="onboarding-wizard__close" aria-label={t('onboarding.close')} onClick={handleClose}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>

        <OnboardingStepSwitch
          wizard={wizard}
          standards={standards}
          currentIndex={currentIndex}
          visibleCount={visible.length}
          createProject={registerProject}
          getProjectInfo={getProjectInfo}
          nextStep={nextStep}
          prevStep={prevStep}
          handleSkipWelcome={handleSkipWelcome}
          handleLaunch={handleLaunch}
        />
      </div>
    </div>
  );
}
