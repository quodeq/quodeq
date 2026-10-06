/**
 * Onboarding-wizard lifecycle: entry state, the derived auto-open decision,
 * and the exit handlers. Moved out of App.jsx (move-only); the
 * pure decision helpers stay exported so the contracts remain unit-testable
 * without mounting the whole App (which needs ~8 providers).
 */
import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { invalidateProjects } from '../../hooks/invalidateProjects.js';
import { selectLandedProject } from '../../hooks/selectLandedProject.js';
import { STEP_WELCOME } from './wizardSteps.js';
import { wasWelcomeSkipped } from './hooks/useWizardDraft.js';
import { WIZARD_SOURCE } from './onboardingVocab.js';
import { PROJECT_SOURCE } from '../../vocab/projectSource.js';
import { NAV_TAB } from '../../vocab/navTab.js';

/**
 * Whether the first-paint onboarding-wizard auto-open effect should fire.
 * "Zero LOCAL projects" alone is not sufficient: a teammate who has
 * connected to a shared repo and is viewing a shared project also reads as
 * zero local projects (state.projects is always the local list per
 * useProjectState), but they already have a real working view open -- the
 * wizard must not cover it uninvited. Likewise a shared repo with published
 * content (sharedHasContent, see useSharedContentSignal) gives the user
 * remote repositories to browse -- the wizard must not open over those
 * either. While the shared signal is still resolving (sharedSettled=false)
 * the decision is DEFERRED: useWizardLifecycle re-evaluates it whenever an
 * input changes.
 */
export function shouldAutoOpenOnboardingWizard({ projectsLoaded, projectsCount, selectedSource, isEvaluating, sharedSettled = true, sharedHasContent = false }) {
  if (!projectsLoaded) return false;
  if ((projectsCount ?? 0) > 0) return false;
  if (selectedSource === PROJECT_SOURCE.SHARED) return false;
  if (isEvaluating) return false;
  if (!sharedSettled) return false;
  if (sharedHasContent) return false;
  return true;
}

/**
 * Exit handlers for the onboarding wizard. The wizard registers the project
 * on its Repo & Scan step (POST /api/projects), well before either exit
 * fires, so both exits that leave a registered project behind (a saved
 * close and a launch) refetch the shared project list, or the new project
 * stays invisible in the Projects tab. Exported so the refetch contract is
 * testable without mounting the whole App.
 */
export function buildWizardHandlers({ state, setWizardEntry, navTab, queryClient }) {
  const refreshProjects = () => {
    invalidateProjects(queryClient).catch((err) => console.warn('[wizard] project list refetch failed:', err));
  };
  return {
    // `cloning`: the add panel closed on a 202, the project arrives through
    // the clone slot (the app re-lists and selects it on the DONE edge).
    // `landed`: the add panel handed a project over (or started its clone);
    // an add ends on the Repositories tab, where the tile or the new card
    // is: from the header that is where the user already stands, from the
    // welcome it is where the job can be watched. A saved exit without
    // `landed` (the X on a resume-setup walk) only refetches.
    onClose: ({ saved, projectId, cloning = false, landed = false }) => {
      setWizardEntry(null);
      if (saved && (projectId || cloning)) {
        refreshProjects();
        state.refreshDashboard?.();
      }
      if (landed) {
        navTab(NAV_TAB.PROJECTS);
        selectLandedProject({ ...state, activeTab: NAV_TAB.PROJECTS }, projectId);
      }
    },
    onLaunch: ({ projectId, repo, scopePath, branch, provider, standardIds, totalTimeLimitS }) => {
      setWizardEntry(null);
      refreshProjects();
      const payload = {
        repo: repo || projectId,
        dimensions: standardIds,
      };
      // The in-progress card names the project that landed, not the global
      // selection, until the run's own project resolves.
      if (projectId) payload.uiProject = projectId;
      if (scopePath) payload.scopePath = scopePath;
      if (branch) payload.branch = branch;
      if (provider?.id) payload.aiCmd = provider.id;
      if (provider?.model) payload.aiModel = provider.model;
      // != null keeps an explicit 0 ("Unlimited") — 0 is falsy but meaningful.
      if (totalTimeLimitS != null) payload.timeLimit = totalTimeLimitS;
      state.liveEvaluation.actions.startEvaluation(payload);
      navTab(NAV_TAB.EVALUATE);
    },
    // The welcome's "go to repositories" once an evaluations repository is connected.
    onGoToRepositories: () => {
      setWizardEntry(null);
      navTab(NAV_TAB.PROJECTS);
    },
  };
}

// Whether the user has something to look at besides the wizard: local
// projects, or a settled shared repo with published content.
function hasWorkingView(state, sharedSignal) {
  return state.projects.length > 0 || (sharedSignal.settled && sharedSignal.hasContent);
}

/**
 * The auto-open, derived from its inputs on every change instead of decided
 * once. It never opens while the project list or the shared signal is still
 * resolving, nor when the user opted out (the skip flag only suppresses
 * auto-open; it never blocks "Add a project" or "Take the tour"). Once the
 * user has a working view (local projects or shared content) a wizard this
 * hook auto-opened that is still on its welcome step steps aside (one the
 * user opened, e.g. "Take the tour", is never closed for them), so a team repo connected mid-session
 * replaces the "nothing here yet" wizard without a reload.
 *
 * `session` records what this page load has already seen: the wizard was
 * opened or closed (a user's close is final; re-popping it on the next input
 * change would fight them), or the user had a working view (deleting the
 * last project, or a disconnect, must not pop a first-run wizard over the
 * app), the entry this hook auto-opened (only that exact entry may be
 * auto-closed), plus the step the open wizard is on.
 */
function useWizardAutoOpen({ state, isEvaluating, sharedSignal, wizardEntry, setWizardEntry, session }) {
  useEffect(() => {
    const seen = session.current;
    if (hasWorkingView(state, sharedSignal)) {
      seen.spent = true;
      if (wizardEntry && wizardEntry === seen.autoEntry && seen.step === STEP_WELCOME) {
        seen.autoEntry = null;
        setWizardEntry(null);
      }
      return;
    }
    if (seen.spent || wizardEntry) return;
    if (!shouldAutoOpenOnboardingWizard({
      projectsLoaded: state.projectsLoaded,
      projectsCount: state.projects.length,
      selectedSource: state.selectedSource,
      isEvaluating,
      sharedSettled: sharedSignal.settled,
      sharedHasContent: sharedSignal.hasContent,
    })) return;
    // The skip is keyed on the server's instance id (undefined until the
    // health poll answers; null for a server without one): deciding before
    // the answer would let a flag from a wiped state folder still count.
    if (state.serverInstanceId === undefined) return;
    if (wasWelcomeSkipped(undefined, state.serverInstanceId)) return;
    const entry = {
      startStep: STEP_WELCOME, isFirstProject: true, source: WIZARD_SOURCE.FIRST_RUN,
      onImportProject: state.handleImportProject, instanceId: state.serverInstanceId,
    };
    Object.assign(seen, { spent: true, autoEntry: entry, step: STEP_WELCOME });
    setWizardEntry(entry);
  }, [state.projectsLoaded, state.projects.length, isEvaluating, state.selectedSource, sharedSignal.settled, sharedSignal.hasContent, state.serverInstanceId]); // eslint-disable-line react-hooks/exhaustive-deps -- re-evaluates on input changes only; wizardEntry and the setter are read current
}

/**
 * Wizard entry state, the derived auto-open (useWizardAutoOpen) and the exit
 * handlers. `onStepChange` lets the mounted wizard report its current step,
 * which is what decides whether shared content may close it.
 *
 * @returns {{ wizardEntry: Object|null, setWizardEntry: Function,
 *   wizardHandlers: { onClose: Function, onLaunch: Function, onGoToRepositories: Function, onStepChange: Function } }}
 */
export function useWizardLifecycle({ state, navTab, isEvaluating, sharedSignal }) {
  const [wizardEntry, setWizardEntry] = useState(null);
  const session = useRef({ spent: false, autoEntry: null, step: null });
  const queryClient = useQueryClient();

  useWizardAutoOpen({ state, isEvaluating, sharedSignal, wizardEntry, setWizardEntry, session });

  // Any close (X, skip for now, import, go to repositories, saved exit,
  // launch) is final for this session.
  const closeAware = (entry) => {
    if (entry === null) Object.assign(session.current, { spent: true, autoEntry: null, step: null });
    setWizardEntry(entry);
  };
  const wizardHandlers = {
    ...buildWizardHandlers({ state, setWizardEntry: closeAware, navTab, queryClient }),
    onStepChange: (step) => { session.current.step = step; },
  };

  return { wizardEntry, setWizardEntry, wizardHandlers };
}
