import WelcomeStep from './steps/WelcomeStep.jsx';
import RepoScanStep from './steps/RepoScanStep.jsx';
import ProviderStep from './steps/ProviderStep.jsx';
import StandardLaunchStep from './steps/StandardLaunchStep.jsx';
import { STEP_WELCOME, STEP_REPO_SCAN, STEP_PROVIDER, STEP_STANDARD_LAUNCH } from '../hooks/useOnboardingWizardHandlers.js';

/**
 * OnboardingWizard.jsx's step-switch JSX (which step component renders for
 * the wizard's current step). Extracted verbatim.
 */
export function OnboardingStepSwitch({
  wizard, standards, currentIndex, visibleCount,
  createProject, getProjectInfo,
  nextStep, prevStep, handleSkipWelcome, handleSavedExit, handleLaunch,
}) {
  return (
    <>
      {wizard.state.step === STEP_WELCOME && (
        <WelcomeStep onStart={() => wizard.goToStep(STEP_REPO_SCAN)} onSkip={handleSkipWelcome} />
      )}

      {wizard.state.step === STEP_REPO_SCAN && (
        <RepoScanStep
          state={wizard.state}
          actions={wizard}
          createProject={createProject}
          getProjectInfo={getProjectInfo}
          onContinue={nextStep}
          onCancel={handleSavedExit}
          stepIndex={currentIndex}
          stepTotal={visibleCount}
        />
      )}

      {wizard.state.step === STEP_PROVIDER && (
        <ProviderStep
          state={wizard.state}
          actions={wizard}
          onContinue={nextStep}
          onBack={prevStep}
          stepIndex={currentIndex}
          stepTotal={visibleCount}
        />
      )}

      {wizard.state.step === STEP_STANDARD_LAUNCH && (
        <StandardLaunchStep
          state={wizard.state}
          actions={wizard}
          standards={standards}
          onLaunch={handleLaunch}
          onCancel={handleSavedExit}
          onBack={prevStep}
          stepIndex={currentIndex}
          stepTotal={visibleCount}
        />
      )}
    </>
  );
}
