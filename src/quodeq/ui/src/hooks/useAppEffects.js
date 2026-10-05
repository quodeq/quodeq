import { useEffect, useRef } from 'react';
import { getGradeFormula } from '../api/index.js';
import { setGradeThresholds } from '../utils/gradeThresholds.js';
import { hydrateVisibleStandardIds } from '../utils/visibleStandards.js';
import { shouldRedirectToRemoteRepositories } from '../appGating.js';
import { buildAssistantActionAppliedHandler } from '../features/assistant/assistantAppBridge.js';
import { ASSISTANT_ACTION_APPLIED_EVENT } from '../constants.js';
import { NAV_TAB } from '../vocab/navTab.js';

// App.jsx's boot-time and navigation-guard effects. Each hook carries the
// rationale for its own effect.

/**
 * Bridges ASSISTANT_ACTION_APPLIED_EVENT window events into the
 * dashboard/scores cache patch + dismissed-list refresh, mirroring the
 * manual dismiss handlers (dismissWithReconcile callers in
 * routes/renderers.jsx).
 */
export function useAssistantActionAppliedEffect({
  applyDelta, bumpDismissRefresh, scheduleReconcileForApply, selectedProject,
}) {
  // The two cache-patch callbacks get a new identity on most renders. Reading
  // them through a ref keeps the listener attached across those renders (a
  // detach/attach cycle could drop an event that lands in between) while the
  // handler still calls the current ones.
  const patchRef = useRef({ applyDelta, bumpDismissRefresh });
  patchRef.current = { applyDelta, bumpDismissRefresh };

  useEffect(() => {
    const handler = buildAssistantActionAppliedHandler({
      applyDelta: (...args) => patchRef.current.applyDelta(...args),
      bumpDismissRefresh: (...args) => patchRef.current.bumpDismissRefresh(...args),
      scheduleDashboardReconcile: scheduleReconcileForApply,
      selectedProject,
    });
    window.addEventListener(ASSISTANT_ACTION_APPLIED_EVENT, handler);
    return () => window.removeEventListener(ASSISTANT_ACTION_APPLIED_EVENT, handler);
  }, [scheduleReconcileForApply, selectedProject]);
}

/**
 * Sync the client-side grade-label thresholds with the server formula at
 * boot so every gauge/badge agrees with the applied Q² parameters. The
 * gradeThresholds store seeds with the Q² defaults, so a failed/absent
 * fetch leaves a sane fallback in place.
 */
export function useGradeFormulaBootSyncEffect() {
  useEffect(() => {
    getGradeFormula()
      .then((d) => setGradeThresholds(d?.current?.gradeThresholds))
      .catch((err) => {
        console.warn('[useAppEffects] grade formula boot fetch failed:', err);
      });
  }, []);
}

// The no-project landing is the default Overview tab itself, not a page
// pushed on top of it.
function isOnNoProjectLanding(activeTab, activePage) {
  return activeTab === NAV_TAB.OVERVIEW && (!activePage || activePage.page === NAV_TAB.OVERVIEW);
}

/**
 * The landing redirect, derived instead of decided once: it re-runs whenever
 * the local project list or the shared signal changes (load settling, a team
 * repo connected mid-session, a first sync landing), so shared content that
 * arrives after boot moves the empty "no projects" Overview to the projects
 * list without a reload. It only ever moves a user who is still on that
 * landing; a tab change alone does not re-run it, so a page the user chose,
 * Overview included, is never yanked away.
 */
export function useInitialLandingEffect({ state, sharedSignal, activeTab, navTab }) {
  const latest = useRef(null);
  latest.current = { selectedSource: state.selectedSource, activePage: state.activePage, activeTab, navTab };
  useEffect(() => {
    const { selectedSource, activePage, activeTab: tab, navTab: go } = latest.current;
    if (!isOnNoProjectLanding(tab, activePage)) return;
    if (shouldRedirectToRemoteRepositories({
      projectsLoaded: state.projectsLoaded,
      projectsCount: state.projects.length,
      selectedSource,
      sharedSettled: sharedSignal.settled,
      sharedHasContent: sharedSignal.hasContent,
      activeTab: tab,
    })) {
      go(NAV_TAB.PROJECTS);
    }
  }, [state.projectsLoaded, sharedSignal.settled, state.projects.length, sharedSignal.hasContent]);
}

/**
 * Reset scroll on project switch — useNavStack handles the same for
 * tab/page changes, but selectedProject lives outside the nav stack.
 * Without this, switching from a project scrolled deep into Projects
 * lands the user partway down the next project's Overview.
 */
export function useProjectScrollResetEffect(selectedProject) {
  useEffect(() => {
    const main = document.querySelector('.app-shell__main-column > .dashboard');
    if (main) main.scrollTop = 0;
  }, [selectedProject]);
}

/**
 * Sync the visible-standards cache (localStorage) with the server's
 * per-project file whenever the selected project settles. This is the
 * earliest point at which "the current project" is known, so it runs
 * before any newly-mounted page reads readVisibleStandardIds() for that
 * project. It migrates a pre-existing local selection up to the server on
 * first run and never throws (see hydrateVisibleStandardIds). Note: a page
 * already mounted with a memoized visible-standards Set keyed on empty deps
 * does not recompute from this. That is a limitation of those read sites, not
 * something this hydration fixes.
 *
 * isStale guards a real race: switching A -> B before A's request resolves
 * must not let A's (now-stale) response overwrite B's selection in the
 * single, per-browser cache. hydrateVisibleStandardIds checks isStale()
 * right before every write it makes (including the migration PUT), so
 * flipping `cancelled` in the cleanup is enough to make a stale response a
 * no-op.
 */
export function useVisibleStandardsHydrationEffect(selectedProject) {
  useEffect(() => {
    if (!selectedProject) return;
    let cancelled = false;
    hydrateVisibleStandardIds(selectedProject, { isStale: () => cancelled });
    return () => { cancelled = true; };
  }, [selectedProject]);
}
