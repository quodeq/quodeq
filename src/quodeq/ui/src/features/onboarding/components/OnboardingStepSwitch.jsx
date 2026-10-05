import WelcomeStep from './steps/WelcomeStep.jsx';
import ConnectStep from './steps/ConnectStep.jsx';
import AnalyzeStep from './steps/AnalyzeStep.jsx';
import ProviderStep from './steps/ProviderStep.jsx';
import StandardLaunchStep from './steps/StandardLaunchStep.jsx';
import { STEP_WELCOME, STEP_CONNECT, STEP_ANALYZE, STEP_PROVIDER, STEP_STANDARD_LAUNCH } from '../wizardSteps.js';
import { WIZARD_SOURCE } from '../onboardingVocab.js';
import { useSharedConnection } from '../../dashboard/hooks/useSharedProjects.js';
import { useSharedDisconnect } from '../../dashboard/hooks/useSharedDisconnect.js';

/**
 * The welcome, fed what already exists: the connected evaluations repository
 * (a passive read of the shared status, no poll), whether local projects
 * exist (an entry with isFirstProject=false) and whether Settings opened it.
 * The connected card's `disconnect` runs the same confirmed disconnect as
 * the strip and Settings; the card then reads the new status and flips back
 * to `connect` in place.
 */
function WelcomeRoute({ wizard, entry, handleSkipWelcome, handleImport }) {
  const { configured, host } = useSharedConnection();
  const disconnect = useSharedDisconnect({ onDisconnected: entry.onSharedDisconnected });
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
      onDisconnect={disconnect}
      onImport={entry.onImportProject ? () => handleImport(entry.onImportProject) : undefined}
      onSkip={handleSkipWelcome}
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
  nextStep, prevStep, handleSkipWelcome, handleImport, handleAdded, handleLaunch, handleClose, onGoToRepositories,
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
        />
      )}

      {step === STEP_CONNECT && (
        <ConnectRoute wizard={wizard} entry={entry} handleClose={handleClose} onGoToRepositories={onGoToRepositories} />
      )}

      {step === STEP_ANALYZE && (
        // useAnalyzeLaunch registers the project (or starts its clone), then hands over.
        <AnalyzeStep state={wizard.state} actions={wizard} onAdded={handleAdded} />
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
          onLaunch={(standardIds) => handleLaunch({ standardIds })}
          onBack={prevStep}
          stepIndex={currentIndex}
          stepTotal={visibleCount}
        />
      )}
    </>
  );
}
