/**
 * Pure app-chrome decision helpers, moved out of App.jsx (move-only): the
 * source-gating and visibility contracts the App component composes into the
 * sidebar/topbar/landing wiring. All exported so they stay unit-testable
 * without mounting the whole App (which needs ~8 providers).
 */

// Project-data tabs (overview/violations/map/history) — module scope so both
// the App component's bounce effect and the exported shouldBounceToEvaluate
// helper below share one definition.
const PROJECT_DATA_TABS = ['overview', 'violations', 'map', 'history'];

/**
 * Whether the "no runs yet" bounce-to-Evaluate effect should fire. Exported
 * (like isSharedSource/buildEvalPrincipal) so the source-gating contract is
 * unit-testable without mounting the whole App.
 *
 * There is no Evaluate flow for shared projects — the guard must reject any
 * non-'local' source outright, independent of hasCurrentProjectRuns (which is
 * computed from the LOCAL project list and can be misleading for a shared
 * selection whose id collides with a local one — see the call site).
 */
export function shouldBounceToEvaluate({ projectsLoaded, projectsCount, selectedProjectInfo, hasCurrentProjectRuns, activeTab, selectedSource }) {
  if (!projectsLoaded) return false;
  if (!projectsCount) return false;
  if (!selectedProjectInfo) return false;
  if (selectedSource !== 'local') return false;
  return !hasCurrentProjectRuns && PROJECT_DATA_TABS.includes(activeTab);
}

/**
 * Whether the TopBar's Evaluate button should be wired up. Shared projects
 * have no Evaluate flow (evaluation is local-only), so the button is omitted
 * outright regardless of project count.
 */
export function shouldShowEvaluateButton(projectsCount, selectedSource) {
  return (projectsCount ?? 0) > 0 && selectedSource !== 'shared';
}

/**
 * The project's friendly name for the topbar/sidebar. A LOCAL selection
 * resolves from the local projects list (selectedProjectInfo / the
 * list-derived selectedDisplayName). A SHARED (remote) selection is NOT in
 * that list, so selectedProjectInfo is null and selectedDisplayName stays
 * equal to the raw UUID -- the anti-UUID guard below would then blank the
 * title entirely. For 'shared', fall back to the resolved sharedProjectInfo
 * payload's name (the same "has data to show" signal shouldShowProjectTabs
 * uses). Returns null while the lists are still unresolved so the UUID never
 * flashes. Exported so the source-gating contract is testable without
 * mounting the whole App.
 */
export function resolveProjectDisplayName({
  selectedProjectInfo, selectedSource, sharedProjectInfo, selectedDisplayName, selectedProject,
}) {
  return selectedProjectInfo?.displayName
    || selectedProjectInfo?.name
    || (selectedSource === 'shared' ? sharedProjectInfo?.name : null)
    || (selectedDisplayName && selectedDisplayName !== selectedProject
          ? selectedDisplayName
          : null);
}

/**
 * Whether the sidebar's project-data tabs (overview/violations/map/history)
 * should render. The local signal is the run count from the LOCAL project
 * list -- which is null/zero for a shared selection with no local mirror, so
 * gating on it alone hides the tabs for shared projects whose pages all work
 * (and a colliding local twin's zero runs would hide them just the same).
 * For 'shared', gate on the resolved sharedProjectInfo instead: the shared
 * info payload carries no runsCount at all, and a project only appears in
 * the shared repo once published with runs, so its info resolving is the
 * "has data to show" signal. Exported (like shouldBounceToEvaluate) so the
 * source-gating contract is testable without mounting the whole App.
 */
export function shouldShowProjectTabs({ selectedSource, hasCurrentProjectRuns, sharedProjectInfo }) {
  if (selectedSource === 'shared') return !!sharedProjectInfo;
  return hasCurrentProjectRuns;
}

/**
 * Sidebar violations/history badge counts. `accumulated` and `dashboard`
 * reset to null the instant the selected project changes (placeholderData is
 * scoped to project+source -- see samePlaceholderScope in api/queryKeys.js),
 * so reading straight off them here is what clears the badges immediately on
 * a project switch instead of leaving the outgoing project's numbers on
 * screen until the new project's fetch lands. Exported so this contract is
 * unit-testable without mounting the whole App.
 */
export function selectSidebarCounts({ filteredAccumulated, accumulated, filteredTrend, dashboard }) {
  return {
    violationsCount: filteredAccumulated?.summary?.totalViolations ?? accumulated?.summary?.totalViolations ?? null,
    historyCount: (filteredTrend || []).length || dashboard?.trend?.length || null,
  };
}

/**
 * One-shot initial-landing decision. With zero local projects the default
 * 'overview' landing is a dead-end empty state; when a configured shared
 * repo has published content, land on the repositories tab instead so the
 * remote projects are visible without scanning anything locally. Only the
 * default 'overview' landing redirects: a user who already navigated
 * elsewhere (settings, help) before the signals settled keeps their page,
 * and a restored 'shared' selection is already a working view. The caller
 * latches the decision once inputs settle, so mid-session deletions or
 * disconnects never yank the user. Exported for unit tests.
 */
export function shouldRedirectToRemoteRepositories({ projectsLoaded, projectsCount, selectedSource, sharedSettled, sharedHasContent, activeTab }) {
  if (!projectsLoaded || !sharedSettled) return false;
  if ((projectsCount ?? 0) > 0) return false;
  if (selectedSource === 'shared') return false;
  if (!sharedHasContent) return false;
  return activeTab === 'overview';
}
