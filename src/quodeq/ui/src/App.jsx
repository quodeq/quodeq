import { lazy, Suspense, useCallback, useMemo, useState, useEffect, useRef } from 'react';
import NavBreadcrumb, { labelFor as navLabelFor } from './features/explorer/components/NavBreadcrumb.jsx';
import UpdateBanner from './features/updates/UpdateBanner.jsx';
import { useSharedContentSignal } from './features/dashboard/hooks/useSharedProjects.js';

const OnboardingWizard = lazy(() => import('./features/onboarding/components/OnboardingWizard.jsx'));
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
import { useStartupTheme, useStartupLoader } from './hooks/useStartupTheme.js';
import { useWizardLifecycle } from './features/onboarding/useWizardLifecycle.js';
import { warmOverviewChunks } from './bootChunks.js';
import { readVisibleStandardIds, hydrateVisibleStandardIds } from './utils/visibleStandards.js';
import { filterTrendByVisibleStandards, filterAccumulatedByVisibleStandards } from './utils/scoreFiltering.js';
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
import {
  MainContent, buildDashboardDataBundle, buildNavigationBundle,
} from './routes/renderers.jsx';
import {
  shouldBounceToEvaluate, shouldShowEvaluateButton, resolveProjectDisplayName,
  shouldShowProjectTabs, selectSidebarCounts, shouldRedirectToRemoteRepositories,
} from './appGating.js';
import {
  buildAssistantSessionPayload, buildAssistantActionAppliedHandler,
} from './features/assistant/assistantAppBridge.js';

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
                  {...wizardHandlers}
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
