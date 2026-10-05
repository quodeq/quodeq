import { clearDraft, markWelcomeSkipped } from './useWizardDraft.js';
import { SETUP_ORDER } from '../wizardSteps.js';
import { SCAN_SUB_STATE } from '../onboardingVocab.js';

// The resume-setup walk (SETUP_ORDER: provider, then standard and launch):
// its step navigation and the launch with the wizard's scope, branch,
// provider and time limit. The analyze screen no longer launches anything.
function resumeWalk({ wizard, onLaunch }) {
  function handleLaunch({ projectId = wizard.state.projectId, repo = wizard.state.repo.value, standardIds }) {
    wizard.startLaunch();
    clearDraft();
    onLaunch({
      projectId,
      repo,
      scopePath: wizard.state.repo.scopePath || null,
      branch: wizard.state.repo.branch || null,
      provider: wizard.state.provider,
      standardIds,
      totalTimeLimitS: wizard.state.totalTimeLimitS,
    });
  }

  function nextStep() {
    const i = SETUP_ORDER.indexOf(wizard.state.step);
    wizard.goToStep(SETUP_ORDER[i + 1] || wizard.state.step);
  }

  function prevStep() {
    const i = SETUP_ORDER.indexOf(wizard.state.step);
    if (i > 0) wizard.goToStep(SETUP_ORDER[i - 1]);
  }

  return { handleLaunch, nextStep, prevStep };
}

/**
 * The wizard's exits: skipping the welcome (to Repositories, and remembered
 * unless opened from Settings), stepping aside for an archive import,
 * closing (a scanned project counts as saved), the add panel's hand-over,
 * and the resume-setup walk (resumeWalk). Each exit clears the draft.
 */
export function useOnboardingWizardHandlers({ wizard, onClose, onLaunch, onGoToRepositories, fromSettings = false }) {
  // A welcome opened from Settings offers no skip; even if one fires, a user
  // who went looking for the welcome has not opted out. Skip lands on Repositories.
  function handleSkipWelcome() {
    if (!fromSettings) markWelcomeSkipped();
    clearDraft();
    onGoToRepositories();
  }

  // The welcome's archive card: the import runs its own native dialog and
  // toasts, so the wizard steps aside first (no skip flag).
  function handleImport(onImportProject) {
    clearDraft();
    onClose({ saved: false });
    onImportProject?.();
  }

  function handleSavedExit() {
    clearDraft();
    onClose({ saved: true, projectId: wizard.state.projectId });
  }

  // The add panel's hand-over: a registered project (the app selects it) or
  // a clone job that started (the Repositories tile carries on, the app
  // selects the project when it lands). Either way the panel closes.
  function handleAdded({ projectId = null, cloning = false }) {
    clearDraft();
    onClose({ saved: true, projectId, cloning });
  }

  function handleClose() {
    if (wizard.state.repoScanSubState === SCAN_SUB_STATE.SCANNED) {
      handleSavedExit();
    } else {
      clearDraft();
      onClose({ saved: false });
    }
  }

  return { handleSkipWelcome, handleImport, handleSavedExit, handleClose, handleAdded, ...resumeWalk({ wizard, onLaunch }) };
}
