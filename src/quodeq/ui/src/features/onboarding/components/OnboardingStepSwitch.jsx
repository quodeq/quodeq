import WelcomeStep from './steps/WelcomeStep.jsx';
import ConnectStep from './steps/ConnectStep.jsx';
import RepoScanStep from './steps/RepoScanStep.jsx';
import ProviderStep from './steps/ProviderStep.jsx';
import StandardLaunchStep from './steps/StandardLaunchStep.jsx';
import { STEP_WELCOME, STEP_CONNECT, STEP_REPO_SCAN, STEP_PROVIDER, STEP_STANDARD_LAUNCH } from '../wizardSteps.js';
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
      // Opens the existing repo-scan flow until the analyze step exists; then start goes to STEP_ANALYZE.
      onStart={() => wizard.goToStep(STEP_REPO_SCAN)}
      onConnect={() => wizard.goToStep(STEP_CONNECT)}
      onImport={entry.onImportProject ? () => handleImport(entry.onImportProject) : undefined}
      onSkip={handleSkipWelcome}
      onGoToRepositories={onGoToRepositories}
      adaptation={adaptation}
    />
  );
}

/**
 * OnboardingWizard.jsx's step-switch JSX (which step component renders for
 * the wizard's current step).
 */
export function OnboardingStepSwitch({
  wizard, entry, standards, currentIndex, visibleCount,
  createProject, getProjectInfo,
  nextStep, prevStep, handleSkipWelcome, handleImport, handleLaunch, onGoToRepositories,
}) {
  return (
    <>
      {wizard.state.step === STEP_WELCOME && (
        <WelcomeRoute
          wizard={wizard}
          entry={entry}
          handleSkipWelcome={handleSkipWelcome}
          handleImport={handleImport}
          onGoToRepositories={onGoToRepositories}
        />
      )}

      {wizard.state.step === STEP_CONNECT && (
        <ConnectStep onBack={() => wizard.goToStep(STEP_WELCOME)} />
      )}

      {wizard.state.step === STEP_REPO_SCAN && (
        <RepoScanStep
          state={wizard.state}
          actions={wizard}
          createProject={createProject}
          getProjectInfo={getProjectInfo}
          onContinue={nextStep}
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
          onBack={prevStep}
          stepIndex={currentIndex}
          stepTotal={visibleCount}
        />
      )}
    </>
  );
}
