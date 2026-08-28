/**
 * Onboarding-wizard lifecycle: entry state, the once-per-session auto-open
 * decision, and the exit handlers. Moved out of App.jsx (move-only); the
 * pure decision helpers stay exported so the contracts remain unit-testable
 * without mounting the whole App (which needs ~8 providers).
 */
import { useEffect, useRef, useState } from 'react';

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
 * the decision is DEFERRED: return false but do not latch, same as the
 * other transient blocks.
 */
export function shouldAutoOpenOnboardingWizard({ projectsLoaded, projectsCount, selectedSource, isEvaluating, sharedSettled = true, sharedHasContent = false }) {
  if (!projectsLoaded) return false;
  if ((projectsCount ?? 0) > 0) return false;
  if (selectedSource === 'shared') return false;
  if (isEvaluating) return false;
  if (!sharedSettled) return false;
  if (sharedHasContent) return false;
  return true;
}

/**
 * Exit handlers for the onboarding wizard. The wizard registers the project
 * on its Repo & Scan step (POST /api/projects), well before either exit
 * fires — so both exits that leave a registered project behind (a saved
 * close and a launch) must reload the projects list, or the new project
 * stays invisible in the Projects tab until an evaluation finishes (the
 * only other path that calls loadProjects). Exported so the reload contract
 * is testable without mounting the whole App.
 */
export function buildWizardHandlers({ state, setWizardEntry, navTab }) {
  return {
    onClose: ({ saved, projectId }) => {
      setWizardEntry(null);
      if (saved && projectId) {
        state.loadProjects?.();
        state.refreshDashboard?.();
      }
    },
    onLaunch: ({ projectId, repo, scopePath, branch, provider, standardIds, totalTimeLimitS }) => {
      setWizardEntry(null);
      state.loadProjects?.();
      const payload = {
        repo: repo || projectId,
        dimensions: standardIds,
      };
      if (scopePath) payload.scopePath = scopePath;
      if (branch) payload.branch = branch;
      if (provider?.id) payload.aiCmd = provider.id;
      if (provider?.model) payload.aiModel = provider.model;
      // != null keeps an explicit 0 ("Unlimited") — 0 is falsy but meaningful.
      if (totalTimeLimitS != null) payload.timeLimit = totalTimeLimitS;
      state.evalLifecycle.handleStartEvaluation(payload);
      navTab('evaluate');
    },
  };
}

/**
 * Wizard entry state + the auto-open-on-first-paint effect.
 *
 * Auto-open is a once-per-session decision. Without the latch, closing the
 * wizard sets wizardEntry → null, which re-fires the effect and re-opens
 * the wizard immediately because projects.length is still 0. The user's
 * close action (X, Maybe later, or Start evaluation) is the signal that the
 * auto-open job is done for this page load.
 *
 * @returns {{ wizardEntry: Object|null, setWizardEntry: Function, wizardHandlers: { onClose: Function, onLaunch: Function } }}
 */
export function useWizardLifecycle({ state, navTab, isEvaluating, sharedSignal }) {
  const [wizardEntry, setWizardEntry] = useState(null);
  const autoOpenedRef = useRef(false);

  // Auto-open wizard on first paint when there are no projects and the user
  // has not explicitly skipped. The skip flag only suppresses auto-open — it
  // never blocks "Add a project" or "Take the tour" buttons.
  useEffect(() => {
    if (autoOpenedRef.current) return;
    if (!state.projectsLoaded) return;
    if (state.projects.length > 0) { autoOpenedRef.current = true; return; }
    if (!shouldAutoOpenOnboardingWizard({
      projectsLoaded: state.projectsLoaded,
      projectsCount: state.projects.length,
      selectedSource: state.selectedSource,
      isEvaluating,
      sharedSettled: sharedSignal.settled,
      sharedHasContent: sharedSignal.hasContent,
    })) {
      // A settled "shared repo has content" outcome is FINAL for this page
      // load, not transient: if it later flips (repo disconnected in
      // Settings, background refresh reveals an emptied repo), the wizard
      // must not pop over the user's working view -- the wall/empty states
      // are the non-modal fallback. Latch here; the remaining blocks
      // (unsettled signal, shared selection, evaluation in flight) stay
      // unlatched so the decision is reconsidered when they lift.
      if (sharedSignal.settled && sharedSignal.hasContent) {
        autoOpenedRef.current = true;
      }
      // Otherwise blocked for a transient reason (shared selection, an
      // evaluation in flight, shared signal still resolving) -- do NOT mark
      // autoOpenedRef: once the block lifts (source switches back to local,
      // the evaluation finishes, the signal settles) while local projects
      // are still zero, the decision must be reconsidered rather than
      // permanently skipped.
      return;
    }
    let skipped = false;
    try { skipped = localStorage.getItem('quodeq_onboarding_skipped') === 'true'; } catch { /* ignore */ }
    autoOpenedRef.current = true;
    if (!skipped) {
      setWizardEntry({ startStep: 'welcome', isFirstProject: true });
    }
  }, [state.projectsLoaded, state.projects.length, isEvaluating, state.selectedSource, sharedSignal.settled, sharedSignal.hasContent]); // eslint-disable-line react-hooks/exhaustive-deps

  const wizardHandlers = buildWizardHandlers({ state, setWizardEntry, navTab });

  return { wizardEntry, setWizardEntry, wizardHandlers };
}
