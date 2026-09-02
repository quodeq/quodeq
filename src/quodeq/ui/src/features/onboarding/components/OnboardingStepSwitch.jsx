import WelcomeStep from './steps/WelcomeStep.jsx';
import RepoScanStep from './steps/RepoScanStep.jsx';
import ProviderStep from './steps/ProviderStep.jsx';
import StandardLaunchStep from './steps/StandardLaunchStep.jsx';

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
      {wizard.state.step === 'welcome' && (
        <WelcomeStep onStart={() => wizard.goToStep('repo-scan')} onSkip={handleSkipWelcome} />
      )}

      {wizard.state.step === 'repo-scan' && (
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

      {wizard.state.step === 'provider' && (
        <ProviderStep
          state={wizard.state}
          actions={wizard}
          onContinue={nextStep}
          onBack={prevStep}
          stepIndex={currentIndex}
          stepTotal={visibleCount}
        />
      )}

      {wizard.state.step === 'standard-launch' && (
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
