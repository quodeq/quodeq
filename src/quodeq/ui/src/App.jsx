import { lazy, Suspense, useCallback, useMemo, useState, useEffect, useRef } from 'react';
import NavBreadcrumb, { labelFor as navLabelFor } from './features/explorer/components/NavBreadcrumb.jsx';
import UpdateBanner from './features/updates/UpdateBanner.jsx';
import { useSharedContentSignal } from './features/dashboard/hooks/useSharedProjects.js';

const DashboardPage = lazy(() => import('./features/dashboard/components/DashboardPage.jsx'));
const ExplorerPage = lazy(() => import('./features/explorer/components/ExplorerPage.jsx'));
const FileDetailPage = lazy(() => import('./features/explorer/components/FileDetailPage.jsx'));
const PrincipleDetailPage = lazy(() => import('./features/explorer/components/PrincipleDetailPage.jsx'));
const FindingDetailPage = lazy(() => import('./features/explorer/components/FindingDetailPage.jsx'));
const ProjectsPage = lazy(() => import('./features/dashboard/components/ProjectsPage.jsx'));
const HistoryPage = lazy(() => import('./features/history/components/HistoryPage.jsx'));
const EvaluateScreen = lazy(() => import('./features/evaluation/components/EvaluateScreen.jsx'));
const SettingsPage = lazy(() => import('./features/settings/components/SettingsPage.jsx'));
const GradeFormulaPage = lazy(() => import('./features/grade-formula/GradeFormulaPage.jsx'));
const StandardsPage = lazy(() => import('./features/standards/StandardsPage.jsx'));
const ViolationsPage = lazy(() => import('./features/violations/components/ViolationsPage.jsx'));
const MapPage = lazy(() => import('./features/map/components/MapPage.jsx'));
const HelpPage = lazy(() => import('./features/help/components/HelpPage.jsx'));
const ComparePage = lazy(() => import('./features/compare/components/ComparePage.jsx'));
const OnboardingWizard = lazy(() => import('./features/onboarding/components/OnboardingWizard.jsx'));
import EmptyState from './components/EmptyState.jsx';
import EmptyStateWithTour from './features/onboarding/components/EmptyStateWithTour.jsx';
import ServerDisconnectedOverlay from './components/ServerDisconnectedOverlay.jsx';
import { useQueryClient } from '@tanstack/react-query';
import { useApi } from './api/ApiContext.jsx';
import { applyMutationDelta } from './api/applyMutationDelta.js';
import { getGradeFormula } from './api/index.js';
import { setGradeThresholds } from './utils/gradeThresholds.js';
import { deriveEvaluatePreselect } from './utils/evaluatePreselect.js';
import { useEvaluationProgress } from './features/evaluation/hooks/useEvaluationProgress.js';
import { computeOverallProgress } from './features/evaluation/components/scanProgressTotals.js';
import LoadingScreen, { FadingLoadingScreen } from './components/LoadingScreen.jsx';
import Sidebar from './components/Sidebar.jsx';
import TopBar from './components/TopBar.jsx';
import { ACTIVE_PROVIDER_KEY, providerKey } from './constants.js';
import { useAppState, formatDayLabel } from './hooks/useAppState.js';
import { useNativeNavBridge } from './hooks/useNativeNavBridge.js';
import { useOneShotGate } from './hooks/useOneShotGate.js';
import { useLinger } from './hooks/useLinger.js';
import { warmOverviewChunks } from './bootChunks.js';

// How long the startup loader stays opaque after its data-hold releases,
// covering the overview's final commit (lazy chart first render).
const STARTUP_LOADER_LINGER_MS = 250;
import { readVisibleStandardIds, hydrateVisibleStandardIds } from './utils/visibleStandards.js';
import { buildProjectRootFile } from './utils/explorerUtils.js';
import { filterTrendByVisibleStandards, filterAccumulatedByVisibleStandards } from './utils/scoreFiltering.js';
import { syncNativeTitlebar } from './utils/nativeTitlebar.js';
import { SidePane, useSidePane } from './features/side-pane/index.js';
import { VerifiedFindingsProvider } from './features/violations/components/verifiedFindingsContext.jsx';
import { BottomDrawer } from './features/drawer/BottomDrawer.jsx';
import { useAssistantDrawer } from './features/assistant/AssistantDrawerProvider.jsx';
import { useAssistantProvider } from './features/settings/hooks/useAssistantProvider.js';
import { deriveAssistantContext } from './features/assistant/useAssistantContext.js';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { EvalLogProvider } from './features/evaluation/eval-log/EvalLogProvider.jsx';
import { ServerLogProvider } from './features/settings/server-log/ServerLogProvider.jsx';
import { OllamaLogProvider } from './features/settings/ollama-log/OllamaLogProvider.jsx';
import { LlamaCppLogProvider } from './features/settings/llamacpp-log/LlamaCppLogProvider.jsx';
import { t } from './strings/index.js';

// Tabs that are reachable with zero projects. `projects` is in here so a
// fresh-install user can land on Projects and add their first one without
// hitting the "no analyzed projects yet" wall.
const NO_PROJECT_TABS = ['projects', 'evaluate', 'standards', 'settings', 'help', 'grade-formula', 'compare'];
const SELF_HANDLED_EMPTY = new Set(['overview', 'map', 'violations', 'history']);

/**
 * Returns whether the app is currently rendering dark, taking the saved
 * theme mode and — when it's 'system' — the OS preference into account.
 * Kept in App so the topbar's theme toggle reflects what's on screen
 * rather than the mode literal.
 */
function useEffectiveDark(themeMode) {
  const [prefersDark, setPrefersDark] = useState(() =>
    typeof window !== 'undefined'
      && window.matchMedia?.('(prefers-color-scheme: dark)').matches
  );
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const mql = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e) => setPrefersDark(e.matches);
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, []);
  if (themeMode === 'dark') return true;
  if (themeMode === 'light') return false;
  return prefersDark;
}

/**
 * Push the on-screen dark/light theme to the native window titlebar
 * whenever it changes, and once more when the pywebview bridge becomes
 * ready (it can inject after first render). No-op in a browser.
 */
function useNativeTitlebarSync(effectiveDark) {
  useEffect(() => {
    syncNativeTitlebar(effectiveDark);
    const onReady = () => syncNativeTitlebar(effectiveDark);
    window.addEventListener('pywebviewready', onReady);
    return () => window.removeEventListener('pywebviewready', onReady);
  }, [effectiveDark]);
}

/**
 * @param {{ serverHealth: Object, evaluation: Object, selectedProject: string, projects: Array, onGoToProjects: Function, onGoToSettings: Function, preselectDims: string[]|undefined }} props
 * @returns {JSX.Element}
 */
function EvaluateCase({ evaluation, selectedProject, projects, onGoToProjects, onGoToSettings, preselectDims }) {
  const { job, jobError, liveViolations, handleStartEvaluation, handleEvalDismiss, cancelEvaluation, startedProject } = evaluation;
  const projectInfo = projects?.find(p => (p.id || p.name) === selectedProject) || null;
  // The in-progress card describes the running job's own project, which can
  // differ from the UI's global selection. Resolve it the same way so the
  // card label follows the job rather than the selection. Before the
  // report-path marker resolves outputProject, the project the job was
  // started for fills the gap; the global selection is never used.
  const jobProjectInfo = job?.outputProject
    ? (projects?.find(p => (p.id || p.name) === job.outputProject) || null)
    : null;
  const startedProjectInfo = startedProject
    ? (projects?.find(p => (p.id || p.name) === startedProject) || null)
    : null;
  return (
    <>
      <EvaluateScreen
        evaluation={{ job, jobError, liveViolations }}
        context={{ selectedProject, projectInfo, jobProjectInfo, startedProjectInfo, preselectDims }}
        actions={{ onStart: handleStartEvaluation, onDismiss: handleEvalDismiss, onCancel: cancelEvaluation, onGoToProjects, onGoToSettings }}
      />
    </>
  );
}

/**
 * @param {{ settings: Object }} props
 * @returns {JSX.Element}
 */
function SettingsCase({ settings, onOpenGradeFormula, onSharedDisconnected }) {
  return (
    <SettingsPage
      theme={{ mode: settings.themeMode, family: settings.themeFamily, onApplyMode: settings.applyMode, onApplyFamily: settings.applyFamily }}
      onOpenGradeFormula={onOpenGradeFormula}
      onSharedDisconnected={onSharedDisconnected}
    />
  );
}

function resolveHistorySelectedRunId(selectedRun, trend) {
  if (selectedRun && selectedRun !== 'latest' && trend.some((t) => t.runId === selectedRun)) return selectedRun;
  return trend.length > 0 ? trend[0].runId : null;
}

function buildDismissPayload(v, fallbackDimension) {
  const fileParts = (v.file || '').split(':');
  const file = fileParts[0];
  const line = v.line ?? (fileParts[1] ? parseInt(fileParts[1], 10) : 0);
  return {
    req: v.req || v.principle,
    file,
    line,
    dimension: v.dimension || fallbackDimension || '',
    severity: v.severity,
    title: v.title || '',
    reason: v.reason,
    reqRefs: v.reqRefs || [],
    context: v.context || '',
    snippet: v.snippet || '',
    scope: v.scope || '',
    endLine: v.endLine || 0,
    principle: v.principle || '',
  };
}

// Shared projects have no mutation route on the backend (dismiss is
// local-only by design, and the same project id can exist in both local and
// shared worlds by design — a dismiss POST for a shared project's id would
// otherwise silently corrupt the LOCAL project's cache with shared-derived
// deltas). Every route renderer below that injects onDismiss calls this
// first: pass `undefined` for shared so the leaf components (EvalCards'
// EvalViolationCard, FileDetailPage's ViolationCard) self-hide the dismiss
// button rather than wiring up a handler that must never fire.
export function isSharedSource(selectedSource) {
  return selectedSource === 'shared';
}

// Project-data tabs (overview/violations/map/history) — module scope so both
// the App component and the exported shouldBounceToEvaluate helper below
// share one definition.
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
 * Build the `navigation` prop bundle ROUTE_RENDERERS consume. Every
 * navigation key a route renderer reads MUST be forwarded here -- a route
 * consuming a key the bundle lacks fails silently at click time (the
 * handler throws mid-event and the UI just doesn't respond; that's how the
 * repositories local/online tab flip broke when handleNavigateReplace was
 * consumed but never forwarded). Exported so producer and consumer can be
 * pinned together in tests without mounting the whole App.
 */
/**
 * The dashboard data bundle handed to every DashboardPage route.
 *
 * Same hazard as buildNavigationBundle, quieter failure: this is an explicit
 * key whitelist, so a field added to useAppState and read by DashboardPage
 * silently arrives as undefined unless it is forwarded here. Nothing throws --
 * the feature just never activates (that is how scoresPending, and the
 * dimension-panel pending state that depends on it, was inert at first).
 * Exported so producer and consumer can be pinned together in tests.
 */
export function buildDashboardDataBundle({ state, sharedHasContent = false }) {
  return {
    selectedProject: state.selectedProject, selectedSource: state.selectedSource, selectedRun: state.selectedRun, projects: state.projects,
    projectsLoaded: state.projectsLoaded,
    projectsLoadFailed: state.projectsLoadFailed,
    onProjectsRetry: state.retryLoadProjects,
    warmup: state.warmup,
    dashboard: state.dashboard, accumulated: state.accumulated, latestAccumulated: state.latestAccumulated, loading: state.loading, isFetching: state.isFetching, error: state.error,
    onRetry: state.refreshDashboardActive,
    scoresPending: state.scoresPending,
    sharedProjectInfo: state.sharedProjectInfo,
    availableRuns: state.availableRuns, dailyRuns: state.dailyRuns, overviewRunIndex: state.overviewRunIndex,
    selectedDisplayName: state.selectedDisplayName,
    granularity: state.granularity, onGranularityChange: state.onGranularityChange,
    sharedHasContent,
  };
}

export function buildNavigationBundle({ state, navTab, navStackLength, isEvaluating, showToast, setWizardEntry, sharedHasContent = false }) {
  return {
    selectedProject: state.selectedProject, selectedSource: state.selectedSource, selectedRun: state.selectedRun, projects: state.projects,
    projectsLoaded: state.projectsLoaded,
    projectsLoadFailed: state.projectsLoadFailed,
    retryLoadProjects: state.retryLoadProjects,
    warmup: state.warmup,
    loadProjects: state.loadProjects,
    handleNavigate: state.handleNavigate, handleNavigateReplace: state.handleNavigateReplace, navPop: state.navPop, handleRunSelect: state.handleRunSelect,
    // navStack + navGoTo let a route unwind history to an earlier entry of
    // its own page (the map's drill-up) instead of pushing a duplicate.
    navStack: state.navStack, navGoTo: state.navGoTo,
    handleProjectChange: state.handleProjectChange, navTab, navStackLength,
    handleDeleteProject: state.handleDeleteProject, handleExportProject: state.handleExportProject, handleRelocateProject: state.handleRelocateProject, handleImportProject: state.handleImportProject,
    historySelectedRun: state.historySelectedRun, setHistorySelectedRun: state.setHistorySelectedRun,
    currentOverviewRun: state.currentOverviewRun, handleRunPrev: state.handleRunPrev, handleRunNext: state.handleRunNext, handleRunLatest: state.handleRunLatest,
    prefetchHandlers: state.prefetchHandlers,
    onAddProject: () => {
      if (isEvaluating) {
        showToast(t('evaluate.busyAddProject'));
        return;
      }
      setWizardEntry({ startStep: 'repo-scan', isFirstProject: state.projects.length === 0 });
    },
    onImportProject: () => {
      if (isEvaluating) {
        showToast(t('evaluate.busyImportProject'));
        return;
      }
      state.handleImportProject();
    },
    onTakeTour: () => {
      if (isEvaluating) {
        showToast(t('evaluate.busyStartTour'));
        return;
      }
      setWizardEntry({ startStep: 'welcome', isFirstProject: true });
    },
    onResumeSetup: (projectId) => {
      if (isEvaluating) {
        showToast(t('evaluate.busyResumeSetup'));
        return;
      }
      setWizardEntry({
        startStep: 'provider',
        isFirstProject: false,
        presetProjectId: projectId,
      });
    },
    // null when the shared repo has no content — consumers use the nullness
    // to hide their "browse remote repositories" affordance.
    onBrowseRemote: sharedHasContent ? () => navTab('projects') : null,
    isEvaluating,
  };
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
 * After the shared repository is disconnected in Settings, a currently
 * 'shared' selection is left pointing at a project that no longer resolves
 * anywhere in the app (its source has no config left) -- the user would be
 * stranded on a broken view. Resolve what handleProjectChange should be
 * called with to recover: the first local project if one exists, otherwise
 * the app's own "no project selected" state (empty id, 'local' source, same
 * as a fresh install / readStoredProject's default -- see useProjectState.js).
 * Returns null when there's nothing to do (selection wasn't 'shared').
 * Exported so the recovery contract is unit-testable without mounting the
 * whole App.
 */
export function resolveSelectionAfterSharedDisconnect({ selectedSource, projects }) {
  if (selectedSource !== 'shared') return null;
  const first = (projects || [])[0];
  const id = first ? (first.id || first.name || first) : '';
  return { id, source: 'local' };
}

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
 * other transient blocks. Exported so this contract is unit-testable
 * without mounting the whole App (which needs ~8 providers).
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

/**
 * Startup-loader hold. Dropping the loader at projectsLoaded hands the user
 * a skeleton flash (loader > skeleton > data) on every boot, so on the
 * default Overview landing it holds until the Overview's data is actually
 * in. It must drop the moment we know no data is coming: load failure,
 * zero local projects, nothing selected, a query error, a restored
 * non-overview tab, or the queries settling empty (`loading` false covers
 * a project with no completed evaluations, whose `accumulated` stays null
 * forever) — every one of those renders its own state and an overlay
 * would wall it off forever. This describes a STATE, not "booting": the
 * caller must scope it with useOneShotGate or a mid-session project
 * switch re-triggers it. Exported for unit tests.
 */
export function shouldShowStartupLoader({
  projectsLoaded, projectsLoadFailed, projectsCount, selectedProject,
  selectedSource, activeTab, dashboard, accumulated, error, loading,
}) {
  if (projectsLoadFailed) return false;
  if (!projectsLoaded) return true;
  if (activeTab !== 'overview') return false;
  if ((projectsCount ?? 0) === 0 && selectedSource !== 'shared') return false;
  if (!selectedProject) return false;
  if (error) return false;
  if (dashboard && accumulated) return false;
  return !!loading;
}

function renderEvalPrincipleDetail(params, props) {
  const { selectedProject, selectedRun, selectedSource } = props.navigation;
  const evalPrincipal = {
    ...params.evalPrincipal,
    project: params.evalPrincipal?.project || selectedProject || '',
    runId: params.evalPrincipal?.runId || selectedRun || '',
  };
  return (
    <PrincipleDetailPage
      evalPrincipal={evalPrincipal}
      severityFilter={params.severity || null}
      onDismiss={isSharedSource(selectedSource) ? undefined : async (v) => {
        // POST returns { scores: { dimensions, summary } } — the rescored
        // payload for this run. PrincipleDetailPage applies it to its
        // local liveScore/liveGrade. The dashboard refetch covers the
        // accumulated (cross-run) rollup separately.
        const payload = { ...buildDismissPayload(v, evalPrincipal.dimension), run_id: evalPrincipal.runId };
        // The evalPrincipal's own project, NOT the global selection: a
        // cross-project entry (Compare's principle jump, a parent
        // dimension's fromProject) must dismiss into the project the
        // finding belongs to — this is the recurring identity-divergence
        // class from the assistant dismiss bug.
        const targetProject = evalPrincipal.project || selectedProject;
        const result = await props.dismissFinding(targetProject, payload);
        props.applyDelta?.(targetProject, result?.scores, result?.delta);
        // One call per suppression mutation: the reconcile marks the project
        // queries stale synchronously AND schedules the debounced active
        // refetch (see scheduleDashboardReconcile in useDashboard.js), so a
        // separate refreshDashboard call here would be redundant.
        props.scheduleDashboardReconcile?.();
        props.bumpDismissRefresh?.();
        return result;
      }}
    />
  );
}

// Exported so unit tests can pin the runId-threading contract without having
// to mount the whole App. Callers from the Violations page must pass the
// dimension's ``fromRunId`` — see ``ViolationsRoute.navigateToPrinciple`` for
// the regression history.
export function buildEvalPrincipal(principleObj, principleGrade, runId) {
  const violations = principleObj.violations || [];
  const compliance = principleObj.compliance || [];
  return {
    principle: principleObj.principle,
    score: principleGrade?.score || null,
    grade: principleGrade?.grade || null,
    dimension: principleObj.dimension || '',
    runId: runId || '',
    principleData: {
      name: principleObj.principle,
      grade: principleGrade?.grade || null,
      violations,
      compliance,
    },
    dimViolations: violations,
    dimCompliance: compliance,
  };
}

function ViolationsRoute({ params, props }) {
  const acc = props.dashboardData.latestAccumulated || props.dashboardData.accumulated;
  const dims = acc?.dimensions || [];
  const nav = props.navigation.handleNavigate;

  const dimMap = new Map(dims.map(d => [d.dimension, d]));
  const principleMap = new Map(
    dims.flatMap(d => (d.principles || []).map(p => [`${d.dimension}\0${p.name || p.principle}`, p]))
  );
  function navigateToPrinciple(principleObj, severity) {
    const dim = dimMap.get(principleObj.dimension);
    const pg = principleMap.get(`${principleObj.dimension}\0${principleObj.principle}`);
    // dim.fromRunId is the run whose data populated this accumulated entry;
    // threading it through lets the dismiss POST carry a real run id so the
    // backend can rescore and project the action into SQL — without this the
    // PrincipleDetail score never moves on dismiss and the entry never lands
    // on the Dismissed tab.
    nav('evalprinciple', {
      evalPrincipal: buildEvalPrincipal(principleObj, pg, dim?.fromRunId),
      severity,
      sourceTab: 'violations',
    });
  }

  function navigateToDimension(row, severity) {
    const dim = row.raw || dimMap.get(row.dimension);
    if (!dim) return;
    // Cell clicks on a dimension row (numeric severity columns or the
    // "violations" total) drill into the dimension's findings — match the
    // project/run pattern by handing FileDetailPage a synthetic file
    // aggregated from the dimension, with the chosen severity preselected.
    const dimFile = buildProjectRootFile([dim], dim.dimension);
    const severityFilter = severity || 'all';
    nav('file', {
      file: dimFile,
      severityFilter,
      runId: dim.fromRunId,
      dateLabel: dim.fromDateLabel,
      sourceTab: 'violations',
    });
  }

  return (
    <ViolationsPage
      data={{
        accumulated: acc,
        accumulatedDimensions: dims,
        selectedProject: props.navigation.selectedProject,
        selectedSource: props.navigation.selectedSource,
        projects: props.navigation.projects,
        projectsLoaded: props.navigation.projectsLoaded,
        projectName: props.dashboardData.selectedDisplayName,
        loading: props.dashboardData.loading,
        isFetching: props.dashboardData.isFetching,
        error: props.dashboardData.error,
        dismissRefreshKey: props.dismissRefreshKey,
      }}
      callbacks={{
        onDimensionClick: (dim) => nav('explorer', { dimension: dim.dimension, runId: dim.fromRunId, dateLabel: dim.fromDateLabel, fromProject: dim.fromProject, sourceTab: 'violations' }),
        onFileClick: (fileObj, opts) => nav('file', { file: fileObj, sourceTab: 'violations', severityFilter: opts?.severity || null }),
        onCellClick: ({ row, severity }) => {
          if (row.type === 'principle' && row.principleObj) {
            navigateToPrinciple(row.principleObj, severity);
          } else {
            navigateToDimension(row, severity);
          }
        },
        onPrincipleClick: (principleObj) => navigateToPrinciple(principleObj),
        // ViolationsPage fires onRefresh on EVERY mount (its tabKey effect),
        // including plain drill-down/back navigation with no mutation --
        // the page remounts on every round trip. onRefresh must stay wired
        // to the lazy refreshDashboard (mark-stale, refetchType:'none') so
        // plain navigation never forces an active refetch of the 10-20 MB
        // dashboard payload. Restore/delete (single + bulk) route through a
        // SEPARATE onReconcile callback via useDismissedFindings, called
        // alongside onRefresh from its four mutation handlers.
        // restore-all/delete-all return a payload applyMutationDelta can't
        // patch (scores:null, delta.isLatest:false), so those need the
        // debounced ACTIVE reconcile — see scheduleDashboardReconcile in
        // useDashboard.js.
        onRefresh: props.refreshDashboard,
        onReconcile: props.scheduleDashboardReconcile,
        onNavigate: nav,
        onRetry: props.dashboardData.onRetry,
      }}
      isDirectNav={props.navigation.navStackLength === 1}
      tabKey={params._tabKey || 0}
      // The by-dimension / by-file / dismissed flip is view state on the SAME
      // screen: it lives in the route entry so back/forward and the crumb see
      // it, but flipping replaces (never pushes) so history doesn't grow.
      // Params are spread forward so _tabKey survives the flip.
      subTab={params.subTab || 'dimension'}
      onSubTabChange={(v) => props.navigation.handleNavigateReplace('violations', { ...params, subTab: v })}
    />
  );
}

// Exported for the same reason as buildEvalPrincipal — a unit-testable pin
// on the per-route onDismiss source-gating contract without mounting the
// whole App (which needs ~8 providers). Calling e.g.
// ROUTE_RENDERERS.file(params, props) just builds the React element tree; it
// doesn't render, so the returned element's props can be asserted on directly.
export const ROUTE_RENDERERS = {
  overview: (params, props) => <DashboardPage data={props.dashboardData} callbacks={{ onNavigate: props.navigation.handleNavigate, onRunSelect: props.navigation.handleRunSelect, onProjectsReload: props.navigation.loadProjects, onRetry: props.dashboardData.onRetry, onProjectsRetry: props.dashboardData.onProjectsRetry }} runMode={false} />,
  violations: (params, props) => <ViolationsRoute params={params} props={props} />,
  map: (params, props) => {
    const acc = props.dashboardData.latestAccumulated || props.dashboardData.accumulated;
    const isDirectNav = props.navigation.navStackLength === 1;
    // The viz drill-down is a real nav-stack entry: drilling into a folder
    // pushes (browser back climbs back out), and navigating up to a path
    // that already sits in the trailing run of map entries unwinds history
    // to it instead of stacking a duplicate. Mode/style toggles replace in
    // place so flipping them never grows history. Params are spread forward
    // on every hop so _tabKey (the fresh-tab-click reset signal) survives.
    const handlePathChange = (path) => {
      const current = params.path || '';
      if (path === current) return;
      const stack = props.navigation.navStack || [];
      for (let i = stack.length - 2; i >= 0 && stack[i].page === 'map'; i--) {
        if ((stack[i].path || '') === path) {
          props.navigation.navGoTo(i);
          return;
        }
      }
      props.navigation.handleNavigate('map', { ...params, path });
    };
    const replaceView = (patch) => props.navigation.handleNavigateReplace('map', { ...params, ...patch });
    return <MapPage
      data={{
        accumulated: acc,
        dashboard: props.dashboardData.dashboard,
        projectName: props.dashboardData.selectedDisplayName,
        projects: props.navigation.projects,
        projectsLoaded: props.navigation.projectsLoaded,
        selectedProject: props.navigation.selectedProject,
        selectedSource: props.navigation.selectedSource,
        loading: props.dashboardData.loading,
        isFetching: props.dashboardData.isFetching,
        error: props.dashboardData.error,
      }}
      callbacks={{ onNavigate: props.navigation.handleNavigate, onRefresh: props.refreshDashboard, onRetry: props.dashboardData.onRetry }}
      nav={{
        path: params.path || '',
        vizStyle: params.vizStyle,
        viewMode: params.viewMode,
        galaxyMode: params.galaxyMode,
        onPathChange: handlePathChange,
        onVizStyleChange: (v) => replaceView({ vizStyle: v }),
        onViewModeChange: (v) => replaceView({ viewMode: v }),
        onGalaxyModeChange: (v) => replaceView({ galaxyMode: v }),
      }}
      isDirectNav={isDirectNav}
      tabKey={params._tabKey || 0}
    />;
  },
  run: (params, props) => <DashboardPage data={props.dashboardData} callbacks={{ onNavigate: props.navigation.handleNavigate, onRetry: props.dashboardData.onRetry, onProjectsRetry: props.dashboardData.onProjectsRetry }} runMode={true} />,
  history: (params, props) => {
    const trend = props.dashboardData.dashboard?.trend || [];
    const runs = props.dashboardData.availableRuns || [];
    const idx = props.dashboardData.overviewRunIndex || 0;
    return (
      <HistoryPage
        trend={trend}
        selection={{
          selectedRunId: resolveHistorySelectedRunId(props.navigation.historySelectedRun, trend),
          selectedRunScore: props.dashboardData.accumulated?.summary?.numericAverage,
        }}
        availableRuns={runs}
        dimensions={{
          accumulatedDimensions: props.dashboardData.accumulated?.dimensions || [],
          lastRun: { date: props.dashboardData.accumulated?.dimensions?.[0]?.fromDateLabel, runId: props.dashboardData.accumulated?.dimensions?.[0]?.fromRunId },
        }}
        callbacks={{
          onRunClick: (runId, dateLabel) => props.navigation.handleNavigate('history-run', { runId, dateLabel }),
          onDimensionClick: (dim) => props.navigation.handleNavigate('explorer', { dimension: dim.dimension, runId: dim.fromRunId, dateLabel: dim.fromDateLabel, fromProject: dim.fromProject }),
          onNavigate: props.navigation.handleNavigate,
          onRunChange: props.navigation.setHistorySelectedRun,
          // Run deletion changes the accumulated rollup the Overview grade is
          // built from — same mutation class as dismiss/restore, so it gets
          // the same debounced ACTIVE reconcile (mark-stale alone never
          // reaches the always-mounted Overview observer).
          onRunDeleted: () => props.scheduleDashboardReconcile?.(),
        }}
        projects={props.navigation.projects}
        projectsLoaded={props.navigation.projectsLoaded}
        selectedProject={props.navigation.selectedProject}
        selectedSource={props.navigation.selectedSource}
        loading={props.dashboardData.loading}
        isFetching={props.dashboardData.isFetching}
        error={props.dashboardData.error}
        onRetry={props.dashboardData.onRetry}
        projectInfo={props.navigation.projects?.find((p) => (p.id || p.name) === props.navigation.selectedProject) || null}
      />
    );
  },
  'history-run': (params, props) => <DashboardPage data={props.dashboardData} callbacks={{ onNavigate: props.navigation.handleNavigate, onRetry: props.dashboardData.onRetry }} runMode={true} />,
  explorer: (params, props) => (
    <ExplorerPage
      project={params.fromProject || props.navigation.selectedProject}
      dimension={params.dimension}
      runId={params.runId}
      dateLabel={params.dateLabel}
      sourceTab={params.sourceTab}
      selectedSource={params.fromSource || props.navigation.selectedSource}
      onNavigate={props.navigation.handleNavigate}
      refreshSignal={props.dashboardData.dashboard}
      trend={props.dashboardData.dashboard?.trend || []}
      granularity={props.dashboardData.granularity}
      onGranularityChange={props.dashboardData.onGranularityChange}
    />
  ),
  evaluate: (params, props) => {
    // Shared projects have no Evaluate flow (evaluation is local-only) --
    // shouldShowEvaluateButton already keeps the TopBar's Evaluate button
    // from ever linking here for a shared selection, but a stale nav-stack
    // entry (e.g. the user was sitting on Evaluate and switched to a shared
    // project) could still land the router on this route. Belt-and-braces:
    // fall back to the Overview, the least-surprising landing spot, rather
    // than rendering a dead-end evaluate screen with no source-appropriate
    // action.
    if (isSharedSource(props.navigation.selectedSource)) {
      return ROUTE_RENDERERS.overview(params, props);
    }
    return <EvaluateCase evaluation={props.evaluation} selectedProject={props.navigation.selectedProject} projects={props.navigation.projects} preselectDims={params.preselectDims} onGoToProjects={() => props.navigation.navTab('projects')} onGoToSettings={() => props.navigation.navTab('settings')} />;
  },
  file: (params, props) => (
    <FileDetailPage
      file={params.file}
      runId={params.runId}
      dateLabel={params.dateLabel}
      severityFilter={params.severityFilter || params.severity || null}
      onDismiss={isSharedSource(props.navigation.selectedSource) ? undefined : async (v) => {
        const payload = { ...buildDismissPayload(v), run_id: params.runId };
        // The entry's own project, not the global selection: a file opened
        // from a cross-project explorer (fromProject) must dismiss into the
        // project the finding belongs to. Same identity rule as the
        // evalprinciple route.
        const targetProject = params.fromProject || props.navigation.selectedProject;
        const result = await props.dismissFinding(targetProject, payload);
        props.applyDelta?.(targetProject, result?.scores, result?.delta);
        // One call per suppression mutation: the reconcile marks the project
        // queries stale synchronously AND schedules the debounced active
        // refetch (see scheduleDashboardReconcile in useDashboard.js), so a
        // separate refreshDashboard call here would be redundant.
        props.scheduleDashboardReconcile?.();
        props.bumpDismissRefresh?.();
        return result;
      }}
    />
  ),
  evalprinciple: renderEvalPrincipleDetail,
  'eval-principle-detail': renderEvalPrincipleDetail,
  finding: (params, props) => (
    <FindingDetailPage
      finding={params.finding}
      principle={params.principle}
      dimension={params.dimension}
      onDismiss={isSharedSource(props.navigation.selectedSource) ? undefined : async (v) => {
        const payload = { ...buildDismissPayload(v, params.dimension), run_id: params.runId };
        // Same identity rule as the file and evalprinciple routes.
        const targetProject = params.fromProject || props.navigation.selectedProject;
        const result = await props.dismissFinding(targetProject, payload);
        props.applyDelta?.(targetProject, result?.scores, result?.delta);
        // One call per suppression mutation: the reconcile marks the project
        // queries stale synchronously AND schedules the debounced active
        // refetch (see scheduleDashboardReconcile in useDashboard.js), so a
        // separate refreshDashboard call here would be redundant.
        props.scheduleDashboardReconcile?.();
        props.bumpDismissRefresh?.();
        return result;
      }}
    />
  ),
  settings: (params, props) => <SettingsCase
    settings={props.settings}
    onOpenGradeFormula={() => props.navigation.handleNavigate('grade-formula')}
    onSharedDisconnected={() => {
      const next = resolveSelectionAfterSharedDisconnect({
        selectedSource: props.navigation.selectedSource,
        projects: props.navigation.projects,
      });
      if (next) props.navigation.handleProjectChange(next.id, next.source);
    }}
  />,
  'grade-formula': (params, props) => <GradeFormulaPage navigation={props.navigation} />,
  projects: (params, props) => <ProjectsPage projects={props.navigation.projects} projectsLoaded={props.navigation.projectsLoaded} selectedProject={props.navigation.selectedProject} isEvaluating={props.navigation.isEvaluating} filters={params.filters} actions={{ onSelect: (id, source) => { props.navigation.handleProjectChange(id, source); props.navigation.navTab('overview'); }, onDelete: props.navigation.handleDeleteProject, onExport: props.navigation.handleExportProject, onRelocate: props.navigation.handleRelocateProject, onAddProject: props.navigation.onAddProject, onImportProject: props.navigation.onImportProject, onResumeSetup: props.navigation.onResumeSetup, onFiltersChange: (filters) => props.navigation.handleNavigateReplace('projects', { filters }), onProjectsReload: props.navigation.loadProjects }} />,
  standards: (params, props) => <StandardsPage onRescan={(dims) => props.navigation.navTab('evaluate', { preselectDims: dims })} />,
  help: () => <HelpPage />,
  compare: (params, props) => (
    <ComparePage
      projects={props.navigation.projects}
      projectsLoaded={props.navigation.projectsLoaded}
      dimension={params.dimension || null}
      onOpenProject={(id, source = 'local') => {
        // Remote fleet rows open through the shared source; the same
        // machinery the projects drawer uses for shared selections.
        props.navigation.handleProjectChange(id, source);
        props.navigation.navTab('overview');
      }}
      // Drill-down is a real nav-stack entry: push from the fleet so the
      // browser back button returns there; replace when switching between
      // dimensions so tab-hopping doesn't grow history.
      onOpenDimension={(key) => props.navigation.handleNavigate('compare', { dimension: key })}
      onSwitchDimension={(key) => props.navigation.handleNavigateReplace('compare', { dimension: key })}
      // Cross-project principle jump: the evalPrincipal carries its own
      // project, so the selection doesn't change and back pops to Compare.
      onOpenEvalPrincipal={(evalPrincipal) => props.navigation.handleNavigate('evalprinciple', { evalPrincipal, sourceTab: 'compare' })}
      // Standings row -> that project's own screen of the SAME dimension
      // (the explorer's cross-project fromProject entry), pushed for the
      // same back-pops-to-Compare contract.
      onOpenProjectDimension={(target) => props.navigation.handleNavigate('explorer', {
        dimension: target.dimName,
        runId: target.runId,
        dateLabel: target.dateLabel,
        fromProject: target.id,
        // The entry's own source, like its own project: the explorer must
        // read a local fromProject from the local API even while the
        // global selection sits on the shared source (and vice versa).
        fromSource: target.source || 'local',
        sourceTab: 'compare',
      })}
      // Head-to-head is a push like the dimension drill-down: back returns
      // to the fleet with the two-project scope still selected.
      duel={params.duel || null}
      onOpenDuel={(ids) => props.navigation.handleNavigate('compare', { duel: ids })}
      onBack={props.navigation.navPop}
    />
  ),
};

// The app-level "no local projects" wall in MainContent. Route pages that
// manage their own empty state (SELF_HANDLED_EMPTY) and the project-free
// tabs (NO_PROJECT_TABS) are never walled; every other page is walled when
// the LOCAL projects list is empty. A shared selection is never walled: its
// data does not live in the local list, and the shared read paths carry
// their own loading/empty states (teammate persona: zero local projects,
// drilling from a shared Overview into file/finding/dimension detail).
// Exported so the source-gating contract is unit-testable without mounting
// MainContent's route renderers.
export function shouldWallEmptyProjects({ page, projects, selectedSource }) {
  if (isSharedSource(selectedSource)) return false;
  if (NO_PROJECT_TABS.includes(page) || SELF_HANDLED_EMPTY.has(page)) return false;
  return !projects || projects.length === 0;
}

// Exported for tests: the session-start payload must carry the selected
// source so remote projects get read-only sessions server-side.
export function buildAssistantSessionPayload({ provider, model, projectId, runId, source }) {
  return { provider, model, projectId, runId, source };
}

/**
 * Handler for the `quodeq:assistant-action-applied` window event, which the
 * assistant's ActionPreviewCard dispatches after a successful apply.
 *
 * Extracted and exported so the post-dismiss convergence contract can be
 * pinned without mounting App (which needs ~8 providers). An assistant
 * dismiss mutates exactly the payloads a manual dismiss does, so it owes the
 * same three follow-ups — see the inline notes on each.
 *
 * @param {{
 *   applyDelta: (project: string, scores: Object, delta: Object) => void,
 *   bumpDismissRefresh: () => void,
 *   scheduleDashboardReconcile?: () => void,
 *   selectedProject: string,
 * }} deps
 * @returns {(event: CustomEvent) => void}
 */
export function buildAssistantActionAppliedHandler({
  applyDelta,
  bumpDismissRefresh,
  scheduleDashboardReconcile,
  selectedProject,
}) {
  return (event) => {
    if (event.detail?.actionType !== 'dismiss_finding') return;
    // Apply the delta first so the currently-visible screen patches in place
    // immediately; the refresh/reconcile below are the eventual-correctness
    // path (e.g. for views the delta doesn't cover).
    // Prefer the delta's own project over the live selectedProject: the
    // apply POST may resolve after the user switched projects, and the
    // delta is frozen to the action's project. Keying the patch on the
    // live selection would write project A's rollup into project B's cache.
    if (event.detail.delta) {
      try {
        applyDelta(
          event.detail.delta?.project || selectedProject,
          event.detail.scores,
          event.detail.delta,
        );
      } catch {
        // Instant patch is best-effort; the refresh/reconcile are the fallback.
      }
    }
    bumpDismissRefresh();
    // Reconcile exactly as the manual dismiss handlers do: the call below
    // marks the project queries stale synchronously (so frozen run views
    // refetch on their next mount) and then actively refetches after the
    // debounce window
    // (see useDismissedFindings.js). Mark-stale alone never reaches the
    // Overview: its useDashboard observer is mounted at the app root and
    // never remounts, and the pywebview window never fires the focus-refetch
    // a browser tab gets. So for any view the delta above doesn't cover --
    // and for an assistant dismiss that returns no delta at all -- the
    // visible screen would keep showing pre-dismiss numbers indefinitely,
    // which reads as "nothing updated". Debounced, so a multi-action apply
    // coalesces into one refetch of the 10-20 MB payload.
    //
    // Unlike applyDelta this keys on the LIVE selectedProject rather than the
    // delta's frozen project. That is safe here
    // where it wouldn't be above: reconciling is a refetch, so aiming it at
    // the wrong project after a mid-flight switch merely re-pulls fresh data;
    // it never writes one project's rollup into another's cache.
    scheduleDashboardReconcile?.();
  };
}

/**
 * @param {{ activePage: { page: string }, props: Object }} params
 * @returns {JSX.Element|null}
 */
function MainContent({ activePage, props }) {
  const { page, ...params } = activePage;
  if (shouldWallEmptyProjects({ page, projects: props.navigation?.projects, selectedSource: props.navigation?.selectedSource })) {
    if (!props.navigation?.projectsLoaded) {
      // Mirror of DashboardPage's gate: a failed startup load must offer a
      // retry instead of an unrecoverable fullscreen spinner.
      if (props.navigation?.projectsLoadFailed) {
        return (
          <EmptyState
            title={t('overview.projectsLoadFailedTitle')}
            description={t('overview.projectsLoadFailedDesc')}
            actionLabel={t('overview.retry')}
            onAction={() => props.navigation.retryLoadProjects?.()}
          />
        );
      }
      // The app-level FadingLoadingScreen overlay covers this state; render
      // nothing here so the loader lives at one stable spot and can fade out.
      return null;
    }
    return (
      <EmptyStateWithTour
        onAdd={() => props.navigation.onAddProject()}
        onTour={() => props.navigation.onTakeTour()}
        onBrowseRemote={props.navigation.onBrowseRemote}
        isEvaluating={props.navigation.isEvaluating}
      />
    );
  }
  const renderer = ROUTE_RENDERERS[page];
  if (renderer) return renderer(params, props);
  return null;
}

/**
 * @param {{ sidebar: JSX.Element, header: JSX.Element|null, content: JSX.Element }} props
 * @returns {JSX.Element}
 */
function AppShell({ sidebar, header, content, drawer, navPending }) {
  return (
    <div className={`app-shell${header ? ' app-shell--with-topbar' : ''}`}>
      {header && <div className="app-shell__topbar">{header}</div>}
      <div className="app-shell__body">
        {sidebar}
        <div className="app-shell__main-column">
          {/* Feedback while a navigation's target page renders (useNavStack
              transition). Must live HERE, outside the scrolling <main>: the
              .dashboard is position:relative, so an absolutely-positioned bar
              inside it anchors to the top of the scrollable CONTENT and
              scrolls out of view — exactly where every detail-page card
              lives, so the one navigation that needed feedback never got it. */}
          {navPending && <div className="nav-pending-bar" aria-hidden="true" />}
          <UpdateBanner />
          <main className="dashboard">
            {content}
          </main>
        </div>
        <SidePane />
        {drawer}
      </div>
    </div>
  );
}

export default function App() {
  const { dismissFinding } = useApi();
  const queryClient = useQueryClient();
  const state = useAppState();
  // Warm the Overview's lazy chunks (DashboardPage + the recharts chart)
  // while the startup loader is up — see bootChunks.js for why page-mount
  // time measured too late.
  useEffect(() => { warmOverviewChunks(); }, []);
  // Passive shared-repo content signal driving the zero-local-projects flow:
  // wizard auto-open (below), the one-shot landing redirect, and the
  // "browse remote repositories" empty-state actions. Same react-query cache
  // as ProjectsPage/Settings — no extra fetching once those mount.
  const sharedSignal = useSharedContentSignal();
  const APP_VERSION = state.serverVersion;
  const selectedProjectInfo = state.projects?.find((p) => (p.id || p.name) === state.selectedProject) || null;
  const [sidebarPinned, setSidebarPinned] = useState(false);
  const [wizardEntry, setWizardEntry] = useState(null);
  // Incremented after every successful dismiss POST so the violations
  // page's dismissed sub-tab knows to refetch its list. Without this, a
  // dismiss made on the principle / file detail page never appeared in the
  // dismissed list until the user switched projects — the list was only
  // fetched once on mount.
  const [dismissRefreshKey, setDismissRefreshKey] = useState(0);
  const bumpDismissRefresh = () => setDismissRefreshKey((k) => k + 1);
  const {
    scheduleDashboardReconcile: scheduleReconcileForApply,
    selectedProject,
  } = state;
  // Shared with the manual dismiss handlers below (buildDismissPayload
  // callers). Patches the dashboard/scores caches from a dismiss response's
  // delta so the Overview updates instantly instead of waiting on a refetch.
  const applyDelta = (project, scores, delta) =>
    applyMutationDelta(queryClient, project, delta && { ...delta, dimensions: scores?.dimensions });
  useEffect(() => {
    const handler = buildAssistantActionAppliedHandler({
      applyDelta,
      bumpDismissRefresh,
      scheduleDashboardReconcile: scheduleReconcileForApply,
      selectedProject,
    });
    window.addEventListener('quodeq:assistant-action-applied', handler);
    return () => window.removeEventListener('quodeq:assistant-action-applied', handler);
  }, [scheduleReconcileForApply, selectedProject]);
  // Auto-open is a once-per-session decision. Without this guard, closing the
  // wizard sets wizardEntry → null, which re-fires this effect and re-opens
  // the wizard immediately because projects.length is still 0. The user's
  // close action (X, Maybe later, or Start evaluation) is the signal that the
  // auto-open job is done for this page load.
  const autoOpenedRef = useRef(false);

  const { showToast } = useSidePane();

  // Live assistant context: the pure derivation reuses the app-state object
  // we already hold (calling useAssistantContext() would spin up a second
  // useAppState and duplicate every dashboard query). The gate provides the
  // active assistant provider/model.
  const assistantGate = useAssistantProvider();
  const assistantCtx = deriveAssistantContext(state, assistantGate);
  const { isOpen: assistantOpen, activeTab: drawerTab, startSession: startAssistantSession } = useAssistantDrawer();
  const { provider: asstProvider, model: asstModel, projectId: asstProjectId, runId: asstRunId, source: asstSource } = assistantCtx;
  // Start (or re-start) the assistant session when the drawer is open and on
  // any provider/model/project/run change while it stays open. startSession
  // dedupes by context key, so re-runs with an unchanged context no-op; a
  // real project/run switch produces a fresh session. We deliberately do NOT
  // start a session while the drawer is closed — sends only originate from the
  // open drawer, so first-open is early enough and avoids needless sessions.
  // Shared projects get READ-ONLY sessions: the backend roots their reads in
  // the shared clone and registers no mutating tools, so the drawer no longer
  // closes on a source switch; the source-keyed session context re-keys instead.
  useEffect(() => {
    if (!assistantOpen || drawerTab !== 'assistant') return;
    startAssistantSession(buildAssistantSessionPayload({
      provider: asstProvider, model: asstModel, projectId: asstProjectId, runId: asstRunId, source: asstSource,
    }));
  }, [assistantOpen, drawerTab, asstProvider, asstModel, asstProjectId, asstRunId, asstSource, startAssistantSession]);

  // Sync the client-side grade-label thresholds with the server formula at
  // boot so every gauge/badge agrees with the applied Q² parameters. The
  // gradeThresholds store seeds with the Q² defaults, so a failed/absent
  // fetch leaves a sane fallback in place.
  useEffect(() => {
    getGradeFormula()
      .then((d) => setGradeThresholds(d?.current?.gradeThresholds))
      .catch(() => {});
  }, []);

  // While an evaluation is running we block any path that would open the
  // onboarding wizard or start a second evaluation — only one job may be in
  // flight at a time.
  const isEvaluating = state.evalLifecycle?.job?.status === 'running';

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
  }, [state.projectsLoaded, state.projects.length, isEvaluating, state.selectedSource, sharedSignal.settled, sharedSignal.hasContent]);

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
  const hasCurrentProjectRuns = (selectedProjectInfo?.runsCount ?? 0) > 0;
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

  const sidebarProvider = (typeof localStorage !== 'undefined' && localStorage.getItem(ACTIVE_PROVIDER_KEY)) || null;
  const sidebarModel = sidebarProvider && typeof localStorage !== 'undefined'
    ? localStorage.getItem(providerKey(sidebarProvider, 'model'))
    : null;
  const { activePage, navStack, navPop, navGoTo, navSwapAt, navTab, activeTab } = state;
  // One-shot: the hold predicate describes a state a mid-session project
  // switch re-enters (Compare's open-project lands on a not-yet-loaded
  // overview); the gate makes sure the fullscreen loader is boot-only —
  // after it drops once, switches get the overview skeleton instead.
  const startupHoldActive = useOneShotGate(shouldShowStartupLoader({
    projectsLoaded: state.projectsLoaded,
    projectsLoadFailed: state.projectsLoadFailed,
    projectsCount: state.projects.length,
    selectedProject: state.selectedProject,
    selectedSource: state.selectedSource,
    activeTab,
    dashboard: state.dashboard,
    accumulated: state.accumulated,
    error: state.error,
    loading: state.loading,
  }));
  // Linger a beat after the hold drops so the overview's final commit (the
  // lazy chart's first render, ~200ms) happens under a still-opaque loader;
  // the fade then reveals a finished page instead of a chart placeholder.
  const showStartupLoader = useLinger(startupHoldActive, STARTUP_LOADER_LINGER_MS);
  // Initial landing: decided exactly once, the first render after both the
  // local projects list and the shared signal have settled (whatever the
  // outcome). Mid-session changes never re-trigger it.
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

  // Native-shell bridge: the macOS Help menu opens tabs by dispatching
  // quodeq:navigate (see _webview_window._install_macos_help_menu).
  useNativeNavBridge(navTab);

  // Reset scroll on project switch — useNavStack handles the same for
  // tab/page changes, but selectedProject lives outside the nav stack.
  // Without this, switching from a project scrolled deep into Projects
  // lands the user partway down the next project's Overview.
  useEffect(() => {
    const main = document.querySelector('.app-shell__main-column > .dashboard');
    if (main) main.scrollTop = 0;
  }, [state.selectedProject]);

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
  useEffect(() => {
    if (!state.selectedProject) return;
    let cancelled = false;
    hydrateVisibleStandardIds(state.selectedProject, { isStale: () => cancelled });
    return () => { cancelled = true; };
  }, [state.selectedProject]);

  const currentDayLabel = useMemo(
    () => formatDayLabel(state.dashboard?.trend, state.currentOverviewRun, state.dailyRuns, state.overviewRunIndex),
    [state.dashboard?.trend, state.currentOverviewRun, state.dailyRuns, state.overviewRunIndex]
  );

  // Resolve whether the UI is currently rendering dark. Used by the
  // topbar's moon/sun toggle so the icon reflects what's on-screen,
  // not just the saved mode preference.
  const effectiveDark = useEffectiveDark(state.settings.themeMode);
  useNativeTitlebarSync(effectiveDark);
  const toggleTheme = () => {
    state.settings.applyMode(effectiveDark ? 'light' : 'dark');
  };

  // Sidebar counts should respect the user's currently-visible standards so
  // they match the numbers shown on the Violations and History pages.
  const visibleSet = useMemo(() => new Set(readVisibleStandardIds()), []);
  const filteredTrend = useMemo(
    () => filterTrendByVisibleStandards(state.dashboard?.trend || [], visibleSet),
    [state.dashboard?.trend, visibleSet]
  );
  const filteredAccumulated = useMemo(
    () => filterAccumulatedByVisibleStandards(state.accumulated, visibleSet, filteredTrend, null),
    [state.accumulated, visibleSet, filteredTrend]
  );

  // Breadcrumb jump-bar data: which siblings a given path segment can swap
  // to. Two levels have a known sibling set — the root tab (the sidebar's
  // main destinations) and the explorer dimension. Levels without one return
  // null and stay plain links.
  const breadcrumbSiblingsFor = useCallback((entry, index) => {
    if (index === 0) {
      if (!state.selectedProject) return null;
      return ['overview', 'violations', 'map', 'history', 'evaluate'].map((id) => ({
        key: id,
        label: navLabelFor({ page: id }),
        current: entry.page === id,
        onSelect: () => (id === 'evaluate'
          ? navTab('evaluate', { preselectDims: deriveEvaluatePreselect(activePage) })
          : navTab(id)),
      }));
    }
    if (entry.page === 'explorer') {
      const dims = filteredAccumulated?.dimensions || [];
      if (dims.length < 2) return null;
      return dims.map((dim) => ({
        key: dim.dimension,
        label: (dim.dimension || '').toLowerCase(),
        current: dim.dimension === entry.dimension,
        onSelect: () => navSwapAt(index, {
          page: 'explorer',
          dimension: dim.dimension,
          runId: dim.fromRunId,
          dateLabel: dim.fromDateLabel,
          fromProject: dim.fromProject,
          sourceTab: entry.sourceTab || 'violations',
        }),
      }));
    }
    return null;
  }, [state.selectedProject, navTab, navSwapAt, activePage, filteredAccumulated]);

  // Live run progress for the topbar chrome (run chip + bottom hairline).
  // Shares the JobStatStrip/ScanProgress query cache entry, so this adds no
  // extra polling.
  const evalJob = state.evalLifecycle?.job;
  const { data: evalProgress } = useEvaluationProgress(isEvaluating ? evalJob?.jobId : undefined, !isEvaluating);
  const topbarRunProgress = useMemo(() => {
    if (!isEvaluating) return null;
    const overall = computeOverallProgress(evalProgress);
    const runningDim = (evalProgress?.dimensions || []).find((d) => d?.state === 'running');
    return {
      dimension: runningDim?.id ? String(runningDim.id).toLowerCase() : null,
      percent: overall.totalFiles > 0 ? overall.overallPct : null,
    };
  }, [isEvaluating, evalProgress]);

  const contentProps = {
    dashboardData: buildDashboardDataBundle({ state, sharedHasContent: sharedSignal.hasContent }),
    navigation: buildNavigationBundle({
      state, navTab, navStackLength: navStack.length,
      isEvaluating, showToast, setWizardEntry,
      sharedHasContent: sharedSignal.hasContent,
    }),
    evaluation: state.evalLifecycle,
    serverHealth: { connected: state.serverConnected, setConnected: state.setServerConnected },
    settings: state.settings,
    refreshDashboard: state.refreshDashboard,
    // Debounced ACTIVE reconcile for suppression mutations (dismiss/restore/
    // delete) — see useDashboard.js. refreshDashboard's refetchType:'none'
    // only marks the cache stale; this actually refetches the always-mounted
    // Overview observer after the 1200ms window, so restore-all/delete-all
    // (whose response can't be patched via applyMutationDelta) and every
    // other suppression mutation converge without waiting for a project
    // switch.
    scheduleDashboardReconcile: state.scheduleDashboardReconcile,
    dismissFinding,
    // Patch the dashboard/scores caches from the dismiss response delta so the
    // Overview updates instantly. Additive — the refreshDashboard /
    // bumpDismissRefresh mechanisms below still run. The delta carries only the
    // mutation shape; the caller folds in the rescored dims from result.scores.
    applyDelta,
    bumpDismissRefresh,
    dismissRefreshKey,
  };

  // Resolve the project's friendly name (see resolveProjectDisplayName): local
  // selections read the local projects list; shared/remote selections (absent
  // from that list) fall back to the resolved sharedProjectInfo name. Until the
  // lists populate this stays null so the raw UUID never flashes.
  const resolvedDisplayName = resolveProjectDisplayName({
    selectedProjectInfo,
    selectedSource: state.selectedSource,
    sharedProjectInfo: state.sharedProjectInfo,
    selectedDisplayName: state.selectedDisplayName,
    selectedProject: state.selectedProject,
  });

  const sidebarCounts = selectSidebarCounts({
    filteredAccumulated, accumulated: state.accumulated, filteredTrend, dashboard: state.dashboard,
  });

  return (
    <>
      <EvalLogProvider>
        <ServerLogProvider>
          <OllamaLogProvider>
            <LlamaCppLogProvider>
              <VerifiedFindingsProvider project={state.selectedProject} source={state.selectedSource}>
              <AppShell
          navPending={state.navPending}
          drawer={<BottomDrawer uiState={assistantCtx.uiState} projectName={resolvedDisplayName}
            onOpenSettings={() => navTab('settings')} />}
          sidebar={
            <Sidebar
              activeTab={activeTab}
              onNavTab={navTab}
              hasEvaluations={state.projects.length > 0}
              showProjectTabs={shouldShowProjectTabs({
                selectedSource: state.selectedSource,
                hasCurrentProjectRuns,
                sharedProjectInfo: state.sharedProjectInfo,
              })}
              // Compare needs two analyzed projects to rank anything; below
              // that the tab is redundant and stays hidden. Remote projects
              // from the shared repository count toward the pair: one local
              // project plus published teammates is a comparable fleet.
              showCompareTab={(() => {
                const localWithRuns = state.projects.filter((p) => (p.runsCount ?? 0) > 0).length;
                return localWithRuns >= 2 || (localWithRuns >= 1 && sharedSignal.hasContent);
              })()}
              selectedSource={state.selectedSource}
              projectInfo={{
                displayName: resolvedDisplayName,
                meta: state.headerMeta,
              }}
              version={APP_VERSION}
              violationsCount={sidebarCounts.violationsCount}
              historyCount={sidebarCounts.historyCount}
              lastEvalAt={state.accumulated?.summary?.lastEvaluatedAt || state.accumulated?.summary?.createdAt || null}
              isPinned={sidebarPinned}
              onPinChange={setSidebarPinned}
            />
          }
          header={
            <TopBar
              projectName={resolvedDisplayName}
              activeTab={activeTab}
              serverConnected={state.serverConnected}
              serverUrl={typeof window !== 'undefined' ? window.location.origin : null}
              provider={sidebarProvider}
              model={sidebarModel}
              selectedSource={state.selectedSource}
              onEvaluate={shouldShowEvaluateButton(state.projects?.length, state.selectedSource) ? (() => navTab('evaluate', { preselectDims: deriveEvaluatePreselect(activePage) })) : null}
              evaluating={state.evalLifecycle?.job?.status === 'running'}
              runProgress={topbarRunProgress}
              onProviderClick={() => navTab('settings')}
              onMenuToggle={() => setSidebarPinned((v) => !v)}
              onSelectProject={() => navTab('projects')}
              breadcrumb={
                <NavBreadcrumb
                  stack={navStack}
                  onGoTo={navGoTo}
                  projectName={resolvedDisplayName}
                  onSelectProject={() => navTab('projects')}
                  siblingsFor={breadcrumbSiblingsFor}
                />
              }
              mobileTitle={navStack.length ? navLabelFor(navStack[navStack.length - 1]) : (activeTab || '')}
              canGoBack={navStack.length > 1}
              onBack={navPop}
              effectiveDark={effectiveDark}
              onToggleTheme={toggleTheme}
            />
          }
          content={
            <>
              {/* One stable mount for the startup loader, OUTSIDE the
                  Suspense: inside it, a lazy chunk's suspension unmounts the
                  loader itself and the plain fallback restarts the fade and
                  tips from zero (a loader-to-loader flash). Out here it
                  covers chunk loads AND holds through the Overview's first
                  data (shouldShowStartupLoader), so boot goes loader ->
                  content with no skeleton in between. */}
              <FadingLoadingScreen
                show={showStartupLoader}
                tips
                warmup={state.warmup}
              />
            <Suspense fallback={<LoadingScreen />}>
              {/* Every route, not just Evaluate. A dead backend is the one
                  failure no page can render around: the Overview's own wall
                  falls back to a bare loading spinner that never resolves, so
                  a killed server read as "quodeq won't start" with nothing
                  on screen to say why or to retry from. */}
              {!state.serverConnected && (
                <ServerDisconnectedOverlay onReconnect={() => state.setServerConnected(true)} />
              )}
              <div className="tab-fade" key={activeTab}>
                <MainContent activePage={activePage} props={contentProps} />
              </div>
              {wizardEntry && (
                <OnboardingWizard
                  entry={wizardEntry}
                  {...buildWizardHandlers({ state, setWizardEntry, navTab })}
                />
              )}
            </Suspense>
            </>
          }
            />
              </VerifiedFindingsProvider>
            </LlamaCppLogProvider>
          </OllamaLogProvider>
        </ServerLogProvider>
      </EvalLogProvider>
    {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
    </>
  );
}
