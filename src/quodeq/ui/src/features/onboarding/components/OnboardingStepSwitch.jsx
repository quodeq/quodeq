import WelcomeStep from './steps/WelcomeStep.jsx';
import ConnectStep from './steps/ConnectStep.jsx';
import AnalyzeStep from './steps/AnalyzeStep.jsx';
import ProviderStep from './steps/ProviderStep.jsx';
import StandardLaunchStep from './steps/StandardLaunchStep.jsx';
import { STEP_WELCOME, STEP_CONNECT, STEP_ANALYZE, STEP_PROVIDER, STEP_STANDARD_LAUNCH } from '../wizardSteps.js';
import { WIZARD_SOURCE } from '../onboardingVocab.js';
import { useSharedConnection } from '../../dashboard/hooks/useSharedProjects.js';

/**
 * The welcome, fed what already exists: the connected evaluations repository
 * (a passive read of the shared status, no poll), whether local projects
 * exist (an entry with isFirstProject=false) and whether Settings opened it.
 */
function WelcomeRoute({ wizard, entry, handleSkipWelcome, handleImport, onGoToRepositories }) {
  const { configured, host } = useSharedConnection();
  const adaptation = {
    connected: configured,
    host,
    hasLocalProjects: entry.isFirstProject === false,
    fromSettings: entry.source === WIZARD_SOURCE.SETTINGS,
  };
  return (
    <WelcomeStep
      onStart={() => wizard.goToStep(STEP_ANALYZE)}
      onConnect={() => wizard.goToStep(STEP_CONNECT)}
      onImport={entry.onImportProject ? () => handleImport(entry.onImportProject) : undefined}
      onSkip={handleSkipWelcome}
      onGoToRepositories={onGoToRepositories}
      adaptation={adaptation}
    />
  );
}

/**
 * The connect step. Reached from the welcome, back returns to it; opened on
 * its own from the Repositories tab (source CONNECT) there is no welcome
 * behind it, so it offers cancel. A started connect lands on the
 * Repositories tab, where the strip shows the download.
 */
function ConnectRoute({ wizard, entry, handleClose, onGoToRepositories }) {
  const fromRepositories = entry.source === WIZARD_SOURCE.CONNECT;
  return (
    <ConnectStep
      onBack={fromRepositories ? undefined : () => wizard.goToStep(STEP_WELCOME)}
      onCancel={handleClose}
      onConnectStarted={onGoToRepositories}
    />
  );
}

/**
 * OnboardingWizard.jsx's step-switch JSX (which step component renders for
 * the wizard's current step). The provider and standard steps are the
 * resume-setup walk (SETUP_ORDER); the provider step opens it, so it has no back.
 */
export function OnboardingStepSwitch({
  wizard, entry, standards, currentIndex, visibleCount,
  nextStep, prevStep, handleSkipWelcome, handleImport, handleLaunch, handleClose, onGoToRepositories,
}) {
  const step = wizard.state.step;
  return (
    <>
      {step === STEP_WELCOME && (
        <WelcomeRoute
          wizard={wizard}
          entry={entry}
          handleSkipWelcome={handleSkipWelcome}
          handleImport={handleImport}
          onGoToRepositories={onGoToRepositories}
        />
      )}

      {step === STEP_CONNECT && (
        <ConnectRoute wizard={wizard} entry={entry} handleClose={handleClose} onGoToRepositories={onGoToRepositories} />
      )}

      {step === STEP_ANALYZE && (
        // Until useAnalyzeLaunch (Task 10) registers the project first, the
        // request's standards go straight to the launch.
        <AnalyzeStep state={wizard.state} actions={wizard} standards={standards} onLaunch={(request) => handleLaunch(request.standardIds)} />
      )}

      {step === STEP_PROVIDER && (
        <ProviderStep
          state={wizard.state}
          actions={wizard}
          onContinue={nextStep}
          stepIndex={currentIndex}
          stepTotal={visibleCount}
        />
      )}

      {step === STEP_STANDARD_LAUNCH && (
        <StandardLaunchStep
          state={wizard.state}
          actions={wizard}
          standards={standards}
          onLaunch={handleLaunch}
          onBack={prevStep}
          stepIndex={currentIndex}
          stepTotal={visibleCount}
        />
      )}
    </>
  );
}
