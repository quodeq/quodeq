import { clearDraft, markWelcomeSkipped } from './useWizardDraft.js';
import { SETUP_ORDER } from '../wizardSteps.js';
import { SCAN_SUB_STATE } from '../onboardingVocab.js';

/**
 * OnboardingWizard.jsx's exit/launch/navigation handlers, extracted
 * verbatim.
 */
export function useOnboardingWizardHandlers({ wizard, onClose, onLaunch, onGoToRepositories, fromSettings = false }) {
  // A welcome opened from Settings offers no skip; even if one fires, a user
  // who went looking for the welcome has not opted out. Skip lands on Repositories.
  function handleSkipWelcome() {
    if (!fromSettings) markWelcomeSkipped();
    clearDraft();
    onGoToRepositories();
  }

  // The welcome's "or import an exported archive": the import runs its own
  // native dialog and toasts, so the wizard steps aside first (no skip flag).
  function handleImport(onImportProject) {
    clearDraft();
    onClose({ saved: false });
    onImportProject?.();
  }

  function handleSavedExit() {
    clearDraft();
    onClose({ saved: true, projectId: wizard.state.projectId });
  }

  function handleClose() {
    if (wizard.state.repoScanSubState === SCAN_SUB_STATE.SCANNED) {
      handleSavedExit();
    } else {
      clearDraft();
      onClose({ saved: false });
    }
  }

  // The analyze screen passes the project it just registered; the resume
  // walk's standard step passes only the standards (its project is in state).
  function handleLaunch({ projectId = wizard.state.projectId, standardIds }) {
    wizard.startLaunch();
    clearDraft();
    onLaunch({
      projectId,
      repo: wizard.state.repo.value,
      scopePath: wizard.state.repo.scopePath || null,
      branch: wizard.state.repo.branch || null,
      provider: wizard.state.provider,
      standardIds,
      totalTimeLimitS: wizard.state.totalTimeLimitS,
    });
  }

  // The resume-setup walk (SETUP_ORDER: provider, then standard and launch).
  function nextStep() {
    const i = SETUP_ORDER.indexOf(wizard.state.step);
    wizard.goToStep(SETUP_ORDER[i + 1] || wizard.state.step);
  }

  function prevStep() {
    const i = SETUP_ORDER.indexOf(wizard.state.step);
    if (i > 0) wizard.goToStep(SETUP_ORDER[i - 1]);
  }

  return { handleSkipWelcome, handleImport, handleSavedExit, handleClose, handleLaunch, nextStep, prevStep };
}
