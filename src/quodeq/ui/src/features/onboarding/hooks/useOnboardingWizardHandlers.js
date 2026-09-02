import { clearDraft, markWelcomeSkipped } from './useWizardDraft.js';

const STEP_ORDER = ['welcome', 'repo-scan', 'provider', 'standard-launch'];

/**
 * OnboardingWizard.jsx's exit/launch/navigation handlers, extracted
 * verbatim.
 */
export function useOnboardingWizardHandlers({ wizard, onClose, onLaunch, providerConfigured }) {
  function handleSkipWelcome() {
    markWelcomeSkipped();
    clearDraft();
    onClose({ saved: false });
  }

  function handleSavedExit() {
    clearDraft();
    onClose({ saved: true, projectId: wizard.state.projectId });
  }

  function handleClose() {
    if (wizard.state.repoScanSubState === 'scanned') {
      handleSavedExit();
    } else {
      clearDraft();
      onClose({ saved: false });
    }
  }

  function handleLaunch(standardIds) {
    wizard.startLaunch();
    clearDraft();
    onLaunch({
      projectId: wizard.state.projectId,
      repo: wizard.state.repo.value,
      scopePath: wizard.state.repo.scopePath || null,
      branch: wizard.state.repo.branch || null,
      provider: wizard.state.provider,
      standardIds,
      totalTimeLimitS: wizard.state.totalTimeLimitS,
    });
  }

  function nextStep() {
    const i = STEP_ORDER.indexOf(wizard.state.step);
    let next = STEP_ORDER[i + 1] || wizard.state.step;
    // Auto-skip Provider if already configured.
    if (next === 'provider' && providerConfigured) next = 'standard-launch';
    wizard.goToStep(next);
  }

  function prevStep() {
    const i = STEP_ORDER.indexOf(wizard.state.step);
    if (i > 0) wizard.goToStep(STEP_ORDER[i - 1]);
  }

  return { handleSkipWelcome, handleSavedExit, handleClose, handleLaunch, nextStep, prevStep };
}
