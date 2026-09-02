import { useEffect, useRef } from 'react';
import { getGradeFormula } from '../api/index.js';
import { setGradeThresholds } from '../utils/gradeThresholds.js';
import { hydrateVisibleStandardIds } from '../utils/visibleStandards.js';
import { shouldBounceToEvaluate, shouldRedirectToRemoteRepositories } from '../appGating.js';
import { buildAssistantActionAppliedHandler } from '../features/assistant/assistantAppBridge.js';

// App.jsx's boot-time and navigation-guard effects, extracted verbatim (see
// App.jsx history for the original inline effects and their rationale
// comments, preserved below on each hook).

// Bridges quodeq:assistant-action-applied window events into the
// dashboard/scores cache patch + dismissed-list refresh, mirroring the
// manual dismiss handlers (dismissWithReconcile callers in
// routes/renderers.jsx).
export function useAssistantActionAppliedEffect({
  applyDelta, bumpDismissRefresh, scheduleReconcileForApply, selectedProject,
}) {
  useEffect(() => {
    const handler = buildAssistantActionAppliedHandler({
      applyDelta,
      bumpDismissRefresh,
      scheduleDashboardReconcile: scheduleReconcileForApply,
      selectedProject,
    });
    window.addEventListener('quodeq:assistant-action-applied', handler);
    return () => window.removeEventListener('quodeq:assistant-action-applied', handler);
  }, [scheduleReconcileForApply, selectedProject]); // eslint-disable-line react-hooks/exhaustive-deps
}

// Sync the client-side grade-label thresholds with the server formula at
// boot so every gauge/badge agrees with the applied Q² parameters. The
// gradeThresholds store seeds with the Q² defaults, so a failed/absent
// fetch leaves a sane fallback in place.
export function useGradeFormulaBootSyncEffect() {
  useEffect(() => {
    getGradeFormula()
      .then((d) => setGradeThresholds(d?.current?.gradeThresholds))
      .catch(() => {});
  }, []);
}

// Project-data tabs (overview/violations/map/history) only make sense once
// the selected project has at least one completed evaluation run. Until
// then, hide them from the sidebar and bounce the user to Evaluate if a
// cached activeTab lands them on a now-hidden tab. The guards below wait
// for /api/projects to resolve and for selectedProjectInfo to populate so
// the bouncer doesn't fire against the transient "no projects loaded yet"
// state on first paint and strand the user on Evaluate.
//
// selectedProjectInfo is always looked up in the LOCAL project list (see
// useProjectState — the list `state.projects` holds only ever comes from
// the local listProjects API). A shared project's id can collide with a
// local one by design (e.g. after a clone-on-add pull); if the local copy
// happens to have zero runs while the shared source has plenty, this
// bounce would incorrectly fire for a shared selection that has real data
// to show. There is no Evaluate for shared projects at all, so it must
// never fire outside 'local' — shouldBounceToEvaluate encodes that.
export function useEvaluateBounceEffect({ state, selectedProjectInfo, hasCurrentProjectRuns }) {
  useEffect(() => {
    if (shouldBounceToEvaluate({
      projectsLoaded: state.projectsLoaded,
      projectsCount: state.projects.length,
      selectedProjectInfo,
      hasCurrentProjectRuns,
      activeTab: state.activeTab,
      selectedSource: state.selectedSource,
    })) {
      state.navTab('evaluate');
    }
  }, [state.projectsLoaded, state.projects.length, selectedProjectInfo, hasCurrentProjectRuns, state.activeTab, state.selectedSource]); // eslint-disable-line react-hooks/exhaustive-deps
}

// Initial landing: decided exactly once, the first render after both the
// local projects list and the shared signal have settled (whatever the
// outcome). Mid-session changes never re-trigger it.
export function useInitialLandingEffect({ state, sharedSignal, activeTab, navTab }) {
  const initialLandingDecidedRef = useRef(false);
  useEffect(() => {
    if (initialLandingDecidedRef.current) return;
    if (!state.projectsLoaded || !sharedSignal.settled) return;
    initialLandingDecidedRef.current = true;
    if (shouldRedirectToRemoteRepositories({
      projectsLoaded: state.projectsLoaded,
      projectsCount: state.projects.length,
      selectedSource: state.selectedSource,
      sharedSettled: sharedSignal.settled,
      sharedHasContent: sharedSignal.hasContent,
      activeTab,
    })) {
      navTab('projects');
    }
  }, [state.projectsLoaded, state.projects.length, state.selectedSource, sharedSignal.settled, sharedSignal.hasContent, activeTab, navTab]);
}

// Reset scroll on project switch — useNavStack handles the same for
// tab/page changes, but selectedProject lives outside the nav stack.
// Without this, switching from a project scrolled deep into Projects
// lands the user partway down the next project's Overview.
export function useProjectScrollResetEffect(selectedProject) {
  useEffect(() => {
    const main = document.querySelector('.app-shell__main-column > .dashboard');
    if (main) main.scrollTop = 0;
  }, [selectedProject]);
}

// Sync the visible-standards cache (localStorage) with the server's
// per-project file whenever the selected project settles. This is the
// earliest point at which "the current project" is known, so it runs
// before any newly-mounted page reads readVisibleStandardIds() for that
// project. It migrates a pre-existing local selection up to the server on
// first run and never throws (see hydrateVisibleStandardIds). Note: pages
// already mounted with a memoized visible-standards Set (e.g. the sidebar
// trend/accumulated filters below, keyed with empty deps) do not
// recompute from this — that is a pre-existing limitation of those read
// sites, not something this hydration fixes.
//
// isStale guards a real race: switching A -> B before A's request resolves
// must not let A's (now-stale) response overwrite B's selection in the
// single, per-browser cache. hydrateVisibleStandardIds checks isStale()
// right before every write it makes (including the migration PUT), so
// flipping `cancelled` in the cleanup is enough to make a stale response a
// no-op.
export function useVisibleStandardsHydrationEffect(selectedProject) {
  useEffect(() => {
    if (!selectedProject) return;
    let cancelled = false;
    hydrateVisibleStandardIds(selectedProject, { isStale: () => cancelled });
    return () => { cancelled = true; };
  }, [selectedProject]);
}
