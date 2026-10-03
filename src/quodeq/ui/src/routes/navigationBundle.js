import { t } from '../strings/index.js';
import { STEP_WELCOME, STEP_REPO_SCAN, STEP_PROVIDER, STEP_CONNECT } from '../features/onboarding/wizardSteps.js';
import { WIZARD_SOURCE } from '../features/onboarding/onboardingVocab.js';
import { NAV_TAB } from '../vocab/navTab.js';

// Every navigation action is blocked while an evaluation runs: the guard
// toasts the action's own "busy" message and swallows the click. Written once
// so a change to the block (or its wording lookup) lands in one place.
function guardedWhileEvaluating({ isEvaluating, showToast, busyKey }, action) {
  return (...args) => {
    if (isEvaluating) {
      showToast(t(busyKey));
      return;
    }
    action(...args);
  };
}

function makeOnAddProject({ isEvaluating, showToast, setWizardEntry, projects }) {
  return guardedWhileEvaluating(
    { isEvaluating, showToast, busyKey: 'evaluate.busyAddProject' },
    () => setWizardEntry({ startStep: STEP_REPO_SCAN, isFirstProject: projects.length === 0, source: WIZARD_SOURCE.ADD }),
  );
}

function makeOnImportProject({ isEvaluating, showToast, handleImportProject }) {
  return guardedWhileEvaluating(
    { isEvaluating, showToast, busyKey: 'evaluate.busyImportProject' },
    () => handleImportProject(),
  );
}

// The welcome, opened by hand: "take the tour" (source ADD, the default) or
// Settings' "show welcome" (source SETTINGS). isFirstProject=false tells the
// welcome there are local projects already; onImportProject backs its
// "or import an exported archive" link.
function makeOnTakeTour({ isEvaluating, showToast, setWizardEntry, projects, onImportProject }) {
  return guardedWhileEvaluating(
    { isEvaluating, showToast, busyKey: 'evaluate.busyStartTour' },
    (source = WIZARD_SOURCE.ADD) => setWizardEntry({
      startStep: STEP_WELCOME, isFirstProject: projects.length === 0, source, onImportProject,
    }),
  );
}

// The Repositories tab's "connect evaluations repository" and the strip's
// "change repository": the wizard opened on its connect step alone. Not
// guarded: connecting an evaluations repository never touches a running
// evaluation. onImportProject rides along like the welcome's entries.
function makeOnConnectEvaluations({ setWizardEntry, onImportProject }) {
  return () => setWizardEntry({ startStep: STEP_CONNECT, source: WIZARD_SOURCE.CONNECT, onImportProject });
}

function makeOnResumeSetup({ isEvaluating, showToast, setWizardEntry }) {
  return guardedWhileEvaluating(
    { isEvaluating, showToast, busyKey: 'evaluate.busyResumeSetup' },
    (projectId) => setWizardEntry({
      startStep: STEP_PROVIDER,
      isFirstProject: false,
      presetProjectId: projectId,
    }),
  );
}

/**
 * Build the `navigation` prop bundle ROUTE_RENDERERS consume. Every navigation
 * key a route renderer reads MUST be forwarded: a route consuming a key the
 * bundle lacks fails silently at click time (the handler throws mid-event and
 * the UI just doesn't respond, which is how the repositories local/online tab
 * flip broke when handleNavigateReplace was consumed but never forwarded). The
 * bundle therefore spreads `state` wholesale rather than re-listing its
 * fields, so a new state field reaches routes without an edit here. The
 * caller-owned and derived fields are listed AFTER the spread so they win over
 * a state key of the same name.
 *
 * Exported so producer and consumer can be pinned together in tests without
 * mounting the whole App.
 *
 * @param {object} args
 * @param {object} args.state - useAppState's bundle; spread in wholesale.
 * @param {(tab: string) => void} args.navTab - switches the top-level tab;
 *   forwarded as-is and also used to build onBrowseRemote.
 * @param {number} args.navStackLength - depth of the in-page back stack.
 * @param {boolean} args.isEvaluating - blocks every navigation action.
 * @param {(msg: string) => void} args.showToast - shows the blocked action's
 *   busy message.
 * @param {(entry: object) => void} args.setWizardEntry - seeds the onboarding
 *   wizard for the add-project entry points.
 * @param {boolean} [args.sharedHasContent] - whether the shared repo has
 *   anything to show, which gates the shared entry point.
 * @returns {object} the navigation bundle.
 */
export function buildNavigationBundle({ state, navTab, navStackLength, isEvaluating, showToast, setWizardEntry, sharedHasContent = false }) {
  const projects = state.projects ?? [];
  const onImportProject = makeOnImportProject({ isEvaluating, showToast, handleImportProject: state.handleImportProject });
  return {
    ...state,
    navTab, navStackLength,
    onAddProject: makeOnAddProject({ isEvaluating, showToast, setWizardEntry, projects }),
    onImportProject,
    onTakeTour: makeOnTakeTour({ isEvaluating, showToast, setWizardEntry, projects, onImportProject }),
    onConnectEvaluations: makeOnConnectEvaluations({ setWizardEntry, onImportProject }),
    onResumeSetup: makeOnResumeSetup({ isEvaluating, showToast, setWizardEntry }),
    // null when the shared repo has no content — consumers use the nullness
    // to hide their "browse remote repositories" affordance.
    onBrowseRemote: sharedHasContent ? () => navTab(NAV_TAB.PROJECTS) : null,
    isEvaluating,
  };
}
