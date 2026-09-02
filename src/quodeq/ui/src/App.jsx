import { useCallback, useMemo, useState, useEffect } from 'react';
import { useSharedContentSignal } from './features/dashboard/hooks/useSharedProjects.js';
import { useQueryClient } from '@tanstack/react-query';
import { useApi } from './api/ApiContext.jsx';
import { applyMutationDelta } from './api/applyMutationDelta.js';
import { useEvaluationProgress } from './features/evaluation/hooks/useEvaluationProgress.js';
import { computeOverallProgress } from './features/evaluation/components/scanProgressTotals.js';
import { readActiveProviderSelection, readActiveProviderModel } from './utils/effectiveProviderSettings.js';
import { useAppState, formatDayLabel } from './hooks/useAppState.js';
import { useNativeNavBridge } from './hooks/useNativeNavBridge.js';
import { useStartupTheme, useStartupLoader } from './hooks/useStartupTheme.js';
import { useWizardLifecycle } from './features/onboarding/useWizardLifecycle.js';
import { warmOverviewChunks } from './bootChunks.js';
import { readVisibleStandardIds } from './utils/visibleStandards.js';
import { filterTrendByVisibleStandards, filterAccumulatedByVisibleStandards } from './utils/scoreFiltering.js';
import { useSidePane } from './features/side-pane/index.js';
import { useAssistantDrawer } from './features/assistant/AssistantDrawerProvider.jsx';
import { useAssistantProvider } from './features/settings/hooks/useAssistantProvider.js';
import { deriveAssistantContext } from './features/assistant/useAssistantContext.js';
import {
  resolveProjectDisplayName, selectSidebarCounts,
} from './appGating.js';
import {
  buildAssistantSessionPayload, buildAssistantActionAppliedHandler,
} from './features/assistant/assistantAppBridge.js';
import {
  useAssistantActionAppliedEffect, useGradeFormulaBootSyncEffect, useEvaluateBounceEffect,
  useInitialLandingEffect, useProjectScrollResetEffect, useVisibleStandardsHydrationEffect,
} from './hooks/useAppEffects.js';
import { buildBreadcrumbSiblingsFor } from './features/side-pane/breadcrumbSiblings.js';
import { buildContentProps } from './appShellProps.js';
import AppMain from './AppMain.jsx';

// Route rendering, gating policies, wizard lifecycle, assistant glue and
// startup chrome moved to their own modules (see routes/renderers.jsx,
// appGating.js, features/onboarding/useWizardLifecycle.js,
// features/assistant/assistantAppBridge.js, hooks/useStartupTheme.js).
// Re-exported here so the existing import surface — tests pin these
// contracts via App.jsx — stays stable.
export {
  isSharedSource, buildEvalPrincipal, ROUTE_RENDERERS,
  resolveSelectionAfterSharedDisconnect, shouldWallEmptyProjects,
  buildDashboardDataBundle, buildNavigationBundle,
} from './routes/renderers.jsx';
export {
  shouldBounceToEvaluate, shouldShowEvaluateButton, resolveProjectDisplayName,
  shouldShowProjectTabs, selectSidebarCounts, shouldRedirectToRemoteRepositories,
} from './appGating.js';
export {
  buildAssistantSessionPayload, buildAssistantActionAppliedHandler,
} from './features/assistant/assistantAppBridge.js';
export { buildWizardHandlers, shouldAutoOpenOnboardingWizard } from './features/onboarding/useWizardLifecycle.js';
export { shouldShowStartupLoader } from './hooks/useStartupTheme.js';

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
  // Shared with the manual dismiss handlers (dismissWithReconcile callers in
  // routes/renderers.jsx). Patches the dashboard/scores caches from a dismiss
  // response's delta so the Overview updates instantly instead of waiting on
  // a refetch.
  const applyDelta = (project, scores, delta) =>
    applyMutationDelta(queryClient, project, delta && { ...delta, dimensions: scores?.dimensions });
  useAssistantActionAppliedEffect({
    applyDelta, bumpDismissRefresh, scheduleReconcileForApply, selectedProject,
  });

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
  useGradeFormulaBootSyncEffect();

  // While an evaluation is running we block any path that would open the
  // onboarding wizard or start a second evaluation — only one job may be in
  // flight at a time.
  const isEvaluating = state.evalLifecycle?.job?.status === 'running';

  // Wizard entry state, the once-per-session auto-open decision, and the
  // exit handlers — see features/onboarding/useWizardLifecycle.js.
  const { wizardEntry, setWizardEntry, wizardHandlers } = useWizardLifecycle({
    state, navTab: state.navTab, isEvaluating, sharedSignal,
  });

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
  useEvaluateBounceEffect({ state, selectedProjectInfo, hasCurrentProjectRuns });

  // NOT memoized on purpose: a per-render read is what makes this pick up a
  // Settings change (active provider/model) without its own change listener.
  const sidebarProvider = readActiveProviderSelection();
  const sidebarModel = readActiveProviderModel(sidebarProvider);
  const { activePage, navStack, navPop, navGoTo, navSwapAt, navTab, activeTab } = state;
  // Boot-only fullscreen loader: one-shot hold plus a short linger — see
  // hooks/useStartupTheme.js for the predicate and gating rationale.
  const showStartupLoader = useStartupLoader({
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
  });
  // Initial landing: decided exactly once, the first render after both the
  // local projects list and the shared signal have settled (whatever the
  // outcome). Mid-session changes never re-trigger it.
  useInitialLandingEffect({ state, sharedSignal, activeTab, navTab });

  // Native-shell bridge: the macOS Help menu opens tabs by dispatching
  // quodeq:navigate (see _webview_window._install_macos_help_menu).
  useNativeNavBridge(navTab);

  // Reset scroll on project switch — useNavStack handles the same for
  // tab/page changes, but selectedProject lives outside the nav stack.
  // Without this, switching from a project scrolled deep into Projects
  // lands the user partway down the next project's Overview.
  useProjectScrollResetEffect(state.selectedProject);

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
  useVisibleStandardsHydrationEffect(state.selectedProject);

  const currentDayLabel = useMemo(
    () => formatDayLabel(state.dashboard?.trend, state.currentOverviewRun, state.dailyRuns, state.overviewRunIndex),
    [state.dashboard?.trend, state.currentOverviewRun, state.dailyRuns, state.overviewRunIndex]
  );

  // Resolve whether the UI is currently rendering dark and keep the native
  // titlebar in sync; the toggle is used by the topbar's moon/sun button so
  // the icon reflects what's on-screen, not just the saved mode preference.
  const { effectiveDark, toggleTheme } = useStartupTheme(state.settings);

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
  // to — see features/side-pane/breadcrumbSiblings.js.
  const breadcrumbSiblingsFor = useCallback(
    buildBreadcrumbSiblingsFor({
      selectedProject: state.selectedProject, navTab, navSwapAt, activePage, filteredAccumulated,
    }),
    [state.selectedProject, navTab, navSwapAt, activePage, filteredAccumulated]
  );

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

  const contentProps = buildContentProps({
    state, sharedSignal, navTab, navStackLength: navStack.length, isEvaluating, showToast, setWizardEntry,
    dismissFinding, applyDelta, bumpDismissRefresh, dismissRefreshKey,
  });

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

  // Bundles every already-computed value AppMain's render tree needs — same
  // values AppMain used to close over inline before this move (see
  // AppMain.jsx). No logic here, just a grouping so App.jsx's own function
  // body stays under the file-size cap without touching hook order above.
  const shell = {
    state, navTab, activeTab, activePage, hasCurrentProjectRuns, sharedSignal, assistantCtx,
    resolvedDisplayName, APP_VERSION, sidebarCounts, sidebarPinned, setSidebarPinned,
    sidebarProvider, sidebarModel, topbarRunProgress, navStack, navGoTo, navPop,
    breadcrumbSiblingsFor, effectiveDark, toggleTheme, showStartupLoader, contentProps,
    wizardEntry, wizardHandlers,
  };

  return <AppMain shell={shell} />;
}
