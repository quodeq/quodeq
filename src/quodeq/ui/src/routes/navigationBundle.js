import { t } from '../strings/index.js';
import { STEP_WELCOME, STEP_REPO_SCAN, STEP_PROVIDER } from '../features/onboarding/wizardSteps.js';

/**
 * Build the `navigation` prop bundle ROUTE_RENDERERS consume. Every
 * navigation key a route renderer reads MUST be forwarded -- a route
 * consuming a key the bundle lacks fails silently at click time (the
 * handler throws mid-event and the UI just doesn't respond; that's how the
 * repositories local/online tab flip broke when handleNavigateReplace was
 * consumed but never forwarded). The bundle therefore spreads `state`
 * wholesale rather than re-listing its fields, so a new state field reaches
 * routes without an edit here. Only the caller-owned and derived fields are
 * listed, and they are listed AFTER the spread so they win over a state key
 * of the same name.
 *
 * Exported so producer and consumer can be pinned together in tests without
 * mounting the whole App.
 */

function makeOnAddProject({ isEvaluating, showToast, setWizardEntry, projects }) {
  return () => {
    if (isEvaluating) {
      showToast(t('evaluate.busyAddProject'));
      return;
    }
    setWizardEntry({ startStep: STEP_REPO_SCAN, isFirstProject: projects.length === 0 });
  };
}

function makeOnImportProject({ isEvaluating, showToast, handleImportProject }) {
  return () => {
    if (isEvaluating) {
      showToast(t('evaluate.busyImportProject'));
      return;
    }
    handleImportProject();
  };
}

function makeOnTakeTour({ isEvaluating, showToast, setWizardEntry }) {
  return () => {
    if (isEvaluating) {
      showToast(t('evaluate.busyStartTour'));
      return;
    }
    setWizardEntry({ startStep: STEP_WELCOME, isFirstProject: true });
  };
}

function makeOnResumeSetup({ isEvaluating, showToast, setWizardEntry }) {
  return (projectId) => {
    if (isEvaluating) {
      showToast(t('evaluate.busyResumeSetup'));
      return;
    }
    setWizardEntry({
      startStep: STEP_PROVIDER,
      isFirstProject: false,
      presetProjectId: projectId,
    });
  };
}

export function buildNavigationBundle({ state, navTab, navStackLength, isEvaluating, showToast, setWizardEntry, sharedHasContent = false }) {
  return {
    ...state,
    navTab, navStackLength,
    onAddProject: makeOnAddProject({ isEvaluating, showToast, setWizardEntry, projects: state.projects }),
    onImportProject: makeOnImportProject({ isEvaluating, showToast, handleImportProject: state.handleImportProject }),
    onTakeTour: makeOnTakeTour({ isEvaluating, showToast, setWizardEntry }),
    onResumeSetup: makeOnResumeSetup({ isEvaluating, showToast, setWizardEntry }),
    // null when the shared repo has no content — consumers use the nullness
    // to hide their "browse remote repositories" affordance.
    onBrowseRemote: sharedHasContent ? () => navTab('projects') : null,
    isEvaluating,
  };
}
