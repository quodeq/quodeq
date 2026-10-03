/**
 * Pure app-chrome decision helpers, moved out of App.jsx (move-only): the
 * source-gating and visibility contracts the App component composes into the
 * sidebar/topbar/landing wiring. All exported so they stay unit-testable
 * without mounting the whole App (which needs ~8 providers).
 */
import { PROJECT_SOURCE } from './vocab/projectSource.js';
import { NAV_TAB } from './vocab/navTab.js';

// Project-data tabs (overview/violations/map/history) — module scope so both
// the App component's bounce effect and the exported shouldBounceToEvaluate
// helper below share one definition.
const PROJECT_DATA_TABS = [NAV_TAB.OVERVIEW, NAV_TAB.VIOLATIONS, NAV_TAB.MAP, NAV_TAB.HISTORY];

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
  if (selectedSource !== PROJECT_SOURCE.LOCAL) return false;
  return !hasCurrentProjectRuns && PROJECT_DATA_TABS.includes(activeTab);
}

/**
 * Whether a selected source has an Evaluate flow at all. Evaluation is
 * local-only server-side, so a 'shared' selection has no route for it —
 * everything else (including an unset/undefined source, which defaults to
 * local) is evaluatable.
 */
export function isEvaluatableSource(selectedSource) {
  return selectedSource !== PROJECT_SOURCE.SHARED;
}

/**
 * Whether the TopBar's Evaluate button should be wired up. Shared projects
 * have no Evaluate flow (evaluation is local-only), so the button is omitted
 * outright regardless of project count.
 */
export function shouldShowEvaluateButton(projectsCount, selectedSource) {
  return (projectsCount ?? 0) > 0 && isEvaluatableSource(selectedSource);
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
    || (selectedSource === PROJECT_SOURCE.SHARED ? sharedProjectInfo?.name : null)
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
  if (selectedSource === PROJECT_SOURCE.SHARED) return !!sharedProjectInfo;
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
// The badge counts majors (critical + major), the number that only moves when
// the code moves; the raw violations total lives on the Violations page.
function majorsOf(summary) {
  const severity = summary?.severity;
  if (!severity || typeof severity !== 'object') return null;
  return (severity.critical || 0) + (severity.major || 0);
}

export function selectSidebarCounts({ filteredAccumulated, accumulated, filteredTrend, dashboard }) {
  return {
    violationsCount: majorsOf(filteredAccumulated?.summary) ?? majorsOf(accumulated?.summary) ?? null,
    historyCount: (filteredTrend || []).length || dashboard?.trend?.length || null,
  };
}

// Compare ranks projects against each other, so it needs at least two.
const COMPARE_MIN_PROJECTS = 2;

/**
 * Compare needs two analyzed projects to rank anything; below that the tab
 * is redundant and stays hidden. Every project that can be ranked counts:
 * local projects with runs and projects published in the connected
 * evaluations repository, in any mix (two published ones with nothing local
 * is a comparable fleet). The inputs are live query data, so the tab appears
 * the moment a connect or a pull brings the count to two. Exported so this
 * contract is unit-testable without mounting the whole App.
 */
export function shouldShowCompareTab({ projects, sharedHasContent, sharedPublishedCount }) {
  const localWithRuns = (projects || []).filter((p) => (p.runsCount ?? 0) > 0).length;
  // Callers that only know "there is published content" count it as one project.
  const published = sharedPublishedCount ?? (sharedHasContent ? 1 : 0);
  return localWithRuns + published >= COMPARE_MIN_PROJECTS;
}

/**
 * The landing decision. With zero local projects the default
 * 'overview' landing is a dead-end empty state; when a configured shared
 * repo has published content, land on the repositories tab instead so the
 * remote projects are visible without scanning anything locally. Only the
 * default 'overview' landing redirects: a user who already navigated
 * elsewhere (settings, help) before the signals settled keeps their page,
 * and a restored 'shared' selection is already a working view. The caller
 * (useInitialLandingEffect) re-runs it when the project list or the shared
 * signal changes, never on a tab change, and only while the user is still on
 * the landing. Exported for unit tests.
 */
export function shouldRedirectToRemoteRepositories({ projectsLoaded, projectsCount, selectedSource, sharedSettled, sharedHasContent, activeTab }) {
  if (!projectsLoaded || !sharedSettled) return false;
  if ((projectsCount ?? 0) > 0) return false;
  if (selectedSource === PROJECT_SOURCE.SHARED) return false;
  if (!sharedHasContent) return false;
  return activeTab === NAV_TAB.OVERVIEW;
}
