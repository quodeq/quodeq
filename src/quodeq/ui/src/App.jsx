import { lazy, Suspense, useMemo, useState, useEffect, useRef } from 'react';
import NavBreadcrumb, { labelFor as navLabelFor } from './features/explorer/components/NavBreadcrumb.jsx';

const DashboardPage = lazy(() => import('./features/dashboard/components/DashboardPage.jsx'));
const ExplorerPage = lazy(() => import('./features/explorer/components/ExplorerPage.jsx'));
const FileDetailPage = lazy(() => import('./features/explorer/components/FileDetailPage.jsx'));
const PrincipleDetailPage = lazy(() => import('./features/explorer/components/PrincipleDetailPage.jsx'));
const FindingDetailPage = lazy(() => import('./features/explorer/components/FindingDetailPage.jsx'));
const ProjectsPage = lazy(() => import('./features/dashboard/components/ProjectsPage.jsx'));
const HistoryPage = lazy(() => import('./features/history/components/HistoryPage.jsx'));
const EvaluateScreen = lazy(() => import('./features/evaluation/components/EvaluateScreen.jsx'));
const SettingsPage = lazy(() => import('./features/settings/components/SettingsPage.jsx'));
const StandardsPage = lazy(() => import('./features/standards/StandardsPage.jsx'));
const ViolationsPage = lazy(() => import('./features/violations/components/ViolationsPage.jsx'));
const MapPage = lazy(() => import('./features/map/components/MapPage.jsx'));
const HelpPage = lazy(() => import('./features/help/components/HelpPage.jsx'));
const OnboardingWizard = lazy(() => import('./features/onboarding/components/OnboardingWizard.jsx'));
import EmptyStateWithTour from './features/onboarding/components/EmptyStateWithTour.jsx';
import ServerDisconnectedOverlay from './components/ServerDisconnectedOverlay.jsx';
import { useApi } from './api/ApiContext.jsx';
import LoadingScreen from './components/LoadingScreen.jsx';
import Sidebar from './components/Sidebar.jsx';
import TopBar from './components/TopBar.jsx';
import { ACTIVE_PROVIDER_KEY, providerKey } from './constants.js';
import ProjectHeader from './components/ProjectHeader.jsx';
import { useAppState, formatDayLabel } from './hooks/useAppState.js';
import { readVisibleStandardIds } from './utils/visibleStandards.js';
import { filterTrendByVisibleStandards, filterAccumulatedByVisibleStandards } from './utils/scoreFiltering.js';
import { SidePane, useSidePane } from './features/side-pane/index.js';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { EvalLogProvider } from './features/evaluation/eval-log/EvalLogProvider.jsx';
import { ServerLogProvider } from './features/settings/server-log/ServerLogProvider.jsx';
import { OllamaLogProvider } from './features/settings/ollama-log/OllamaLogProvider.jsx';

// Tabs that are reachable with zero projects. `projects` is in here so a
// fresh-install user can land on Projects and add their first one without
// hitting the "no analyzed projects yet" wall.
const NO_PROJECT_TABS = ['projects', 'evaluate', 'standards', 'settings', 'help'];
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
 * @param {{ serverHealth: Object, evaluation: Object, selectedProject: string }} props
 * @returns {JSX.Element}
 */
function EvaluateCase({ serverHealth, evaluation, selectedProject, projects, onGoToProjects, onGoToSettings }) {
  const { connected, setConnected } = serverHealth;
  const { job, jobError, liveViolations, handleStartEvaluation, handleEvalDismiss, cancelEvaluation } = evaluation;
  const projectInfo = projects?.find(p => (p.id || p.name) === selectedProject) || null;
  return (
    <>
      {!connected && <ServerDisconnectedOverlay onReconnect={() => setConnected(true)} />}
      <EvaluateScreen
        evaluation={{ job, jobError, liveViolations }}
        context={{ selectedProject, projectInfo }}
        actions={{ onStart: handleStartEvaluation, onDismiss: handleEvalDismiss, onCancel: cancelEvaluation, onGoToProjects, onGoToSettings }}
      />
    </>
  );
}

/**
 * @param {{ settings: Object }} props
 * @returns {JSX.Element}
 */
function SettingsCase({ settings }) {
  return (
    <SettingsPage
      theme={{ mode: settings.themeMode, family: settings.themeFamily, onApplyMode: settings.applyMode, onApplyFamily: settings.applyFamily }}
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

function renderEvalPrincipleDetail(params, props) {
  const { selectedProject, selectedRun } = props.navigation;
  const evalPrincipal = {
    ...params.evalPrincipal,
    project: params.evalPrincipal?.project || selectedProject || '',
    runId: params.evalPrincipal?.runId || selectedRun || '',
  };
  return (
    <PrincipleDetailPage
      evalPrincipal={evalPrincipal}
      severityFilter={params.severity || null}
      onDismiss={(v) => {
        props.dismissFinding(selectedProject, buildDismissPayload(v, evalPrincipal.dimension))
          .then(() => props.refreshDashboard?.())
          .catch((e) => console.error('[Dismiss] failed:', e));
      }}
    />
  );
}

function buildEvalPrincipal(principleObj, principleGrade) {
  const violations = principleObj.violations || [];
  const compliance = principleObj.compliance || [];
  return {
    principle: principleObj.principle,
    score: principleGrade?.score || null,
    grade: principleGrade?.grade || null,
    dimension: principleObj.dimension || '',
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
    nav('evalprinciple', { evalPrincipal: buildEvalPrincipal(principleObj, pg), severity, sourceTab: 'violations' });
  }

  function navigateToDimension(row, severity) {
    const dim = row.raw || dimMap.get(row.dimension);
    if (!dim) return;
    nav('explorer', { dimension: dim.dimension, runId: dim.fromRunId, dateLabel: dim.fromDateLabel, fromProject: dim.fromProject, severity, sourceTab: 'violations' });
  }

  return (
    <ViolationsPage
      data={{
        accumulated: acc,
        accumulatedDimensions: dims,
        selectedProject: props.navigation.selectedProject,
        projects: props.navigation.projects,
        projectsLoaded: props.navigation.projectsLoaded,
        projectName: props.dashboardData.selectedDisplayName,
        loading: props.dashboardData.loading,
        isFetching: props.dashboardData.isFetching,
      }}
      callbacks={{
        onDimensionClick: (dim) => nav('explorer', { dimension: dim.dimension, runId: dim.fromRunId, dateLabel: dim.fromDateLabel, fromProject: dim.fromProject, sourceTab: 'violations' }),
        onFileClick: (fileObj) => nav('file', { file: fileObj, sourceTab: 'violations' }),
        onCellClick: ({ row, severity }) => {
          if (row.type === 'principle' && row.principleObj) {
            navigateToPrinciple(row.principleObj, severity);
          } else {
            navigateToDimension(row, severity);
          }
        },
        onPrincipleClick: (principleObj) => navigateToPrinciple(principleObj),
        onRefresh: props.refreshDashboard,
        onNavigate: nav,
      }}
      isDirectNav={props.navigation.navStackLength === 1}
      tabKey={params._tabKey || 0}
    />
  );
}

const ROUTE_RENDERERS = {
  overview: (params, props) => <DashboardPage data={props.dashboardData} callbacks={{ onNavigate: props.navigation.handleNavigate, onRunSelect: props.navigation.handleRunSelect, onProjectsReload: props.navigation.loadProjects }} runMode={false} />,
  violations: (params, props) => <ViolationsRoute params={params} props={props} />,
  map: (params, props) => {
    const acc = props.dashboardData.latestAccumulated || props.dashboardData.accumulated;
    const isDirectNav = props.navigation.navStackLength === 1;
    return <MapPage
      data={{
        accumulated: acc,
        dashboard: props.dashboardData.dashboard,
        projectName: props.dashboardData.selectedDisplayName,
        projects: props.navigation.projects,
        projectsLoaded: props.navigation.projectsLoaded,
        selectedProject: props.navigation.selectedProject,
        loading: props.dashboardData.loading,
        isFetching: props.dashboardData.isFetching,
      }}
      callbacks={{ onNavigate: props.navigation.handleNavigate, onRefresh: props.refreshDashboard }}
      isDirectNav={isDirectNav}
      tabKey={params._tabKey || 0}
    />;
  },
  run: (params, props) => <DashboardPage data={props.dashboardData} callbacks={{ onNavigate: props.navigation.handleNavigate }} runMode={true} />,
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
          onRunDeleted: () => props.refreshDashboard?.(),
        }}
        projects={props.navigation.projects}
        projectsLoaded={props.navigation.projectsLoaded}
        selectedProject={props.navigation.selectedProject}
        loading={props.dashboardData.loading}
        isFetching={props.dashboardData.isFetching}
        projectInfo={props.navigation.projects?.find((p) => (p.id || p.name) === props.navigation.selectedProject) || null}
      />
    );
  },
  'history-run': (params, props) => <DashboardPage data={props.dashboardData} callbacks={{ onNavigate: props.navigation.handleNavigate }} runMode={true} />,
  explorer: (params, props) => (
    <ExplorerPage
      project={params.fromProject || props.navigation.selectedProject}
      dimension={params.dimension}
      runId={params.runId}
      dateLabel={params.dateLabel}
      onNavigate={props.navigation.handleNavigate}
      refreshSignal={props.dashboardData.dashboard}
      trend={props.dashboardData.dashboard?.trend || []}
    />
  ),
  evaluate: (params, props) => <EvaluateCase serverHealth={props.serverHealth} evaluation={props.evaluation} selectedProject={props.navigation.selectedProject} projects={props.navigation.projects} onGoToProjects={() => props.navigation.navTab('projects')} onGoToSettings={() => props.navigation.navTab('settings')} />,
  file: (params) => <FileDetailPage file={params.file} runId={params.runId} dateLabel={params.dateLabel} />,
  evalprinciple: renderEvalPrincipleDetail,
  'eval-principle-detail': renderEvalPrincipleDetail,
  finding: (params, props) => (
    <FindingDetailPage
      finding={params.finding}
      principle={params.principle}
      dimension={params.dimension}
      onDismiss={(v) => {
        props.dismissFinding(props.navigation.selectedProject, buildDismissPayload(v, params.dimension))
          .then(() => props.refreshDashboard?.())
          .catch((e) => console.error('[Dismiss] failed:', e));
      }}
    />
  ),
  settings: (params, props) => <SettingsCase settings={props.settings} />,
  projects: (params, props) => <ProjectsPage projects={props.navigation.projects} selectedProject={props.navigation.selectedProject} isEvaluating={props.navigation.isEvaluating} actions={{ onSelect: (id) => { props.navigation.handleProjectChange(id); props.navigation.navTab('overview'); }, onDelete: props.navigation.handleDeleteProject, onExport: props.navigation.handleExportProject, onRelocate: props.navigation.handleRelocateProject, onAddProject: props.navigation.onAddProject, onResumeSetup: props.navigation.onResumeSetup }} />,
  standards: () => <StandardsPage />,
  help: () => <HelpPage />,
};

/**
 * @param {{ activePage: { page: string }, props: Object }} params
 * @returns {JSX.Element|null}
 */
function MainContent({ activePage, props }) {
  const { page, ...params } = activePage;
  if (!NO_PROJECT_TABS.includes(page) && !SELF_HANDLED_EMPTY.has(page)) {
    const projects = props.navigation?.projects;
    if (!projects || projects.length === 0) {
      if (!props.navigation?.projectsLoaded) return <LoadingScreen />;
      return (
        <EmptyStateWithTour
          onAdd={() => props.navigation.onAddProject()}
          onTour={() => props.navigation.onTakeTour()}
          isEvaluating={props.navigation.isEvaluating}
        />
      );
    }
  }
  const renderer = ROUTE_RENDERERS[page];
  if (renderer) return renderer(params, props);
  return null;
}

/**
 * @param {{ sidebar: JSX.Element, header: JSX.Element|null, content: JSX.Element }} props
 * @returns {JSX.Element}
 */
function AppShell({ sidebar, header, content }) {
  return (
    <div className={`app-shell${header ? ' app-shell--with-topbar' : ''}`}>
      {header && <div className="app-shell__topbar">{header}</div>}
      <div className="app-shell__body">
        {sidebar}
        <div className="app-shell__main-column">
          <main className="dashboard">
            {content}
          </main>
        </div>
        <SidePane />
      </div>
    </div>
  );
}

export default function App() {
  const { dismissFinding } = useApi();
  const state = useAppState();
  const APP_VERSION = state.serverVersion;
  const selectedProjectInfo = state.projects?.find((p) => (p.id || p.name) === state.selectedProject) || null;
  const [sidebarPinned, setSidebarPinned] = useState(false);
  const [wizardEntry, setWizardEntry] = useState(null);
  // Auto-open is a once-per-session decision. Without this guard, closing the
  // wizard sets wizardEntry → null, which re-fires this effect and re-opens
  // the wizard immediately because projects.length is still 0. The user's
  // close action (X, Maybe later, or Start evaluation) is the signal that the
  // auto-open job is done for this page load.
  const autoOpenedRef = useRef(false);

  const { showToast } = useSidePane();

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
    if (isEvaluating) return;
    let skipped = false;
    try { skipped = localStorage.getItem('quodeq_onboarding_skipped') === 'true'; } catch { /* ignore */ }
    autoOpenedRef.current = true;
    if (!skipped) {
      setWizardEntry({ startStep: 'welcome', isFirstProject: true });
    }
  }, [state.projectsLoaded, state.projects.length, isEvaluating]);

  // Project-data tabs (overview/violations/map/history) only make sense once
  // the selected project has at least one completed evaluation run. Until
  // then, hide them from the sidebar and bounce the user to Evaluate if a
  // cached activeTab lands them on a now-hidden tab. The guards below wait
  // for /api/projects to resolve and for selectedProjectInfo to populate so
  // the bouncer doesn't fire against the transient "no projects loaded yet"
  // state on first paint and strand the user on Evaluate.
  const PROJECT_DATA_TABS = ['overview', 'violations', 'map', 'history'];
  const hasCurrentProjectRuns = (selectedProjectInfo?.runsCount ?? 0) > 0;
  useEffect(() => {
    if (!state.projectsLoaded) return;
    if (state.projects.length === 0) return;
    if (!selectedProjectInfo) return;
    if (!hasCurrentProjectRuns && PROJECT_DATA_TABS.includes(state.activeTab)) {
      state.navTab('evaluate');
    }
  }, [state.projectsLoaded, state.projects.length, selectedProjectInfo, hasCurrentProjectRuns, state.activeTab]); // eslint-disable-line react-hooks/exhaustive-deps

  const sidebarProvider = (typeof localStorage !== 'undefined' && localStorage.getItem(ACTIVE_PROVIDER_KEY)) || null;
  const sidebarModel = sidebarProvider && typeof localStorage !== 'undefined'
    ? localStorage.getItem(providerKey(sidebarProvider, 'model'))
    : null;
  const { activePage, navStack, navPop, navGoTo, navTab, activeTab } = state;

  const currentDayLabel = useMemo(
    () => formatDayLabel(state.dashboard?.trend, state.currentOverviewRun, state.dailyRuns, state.overviewRunIndex),
    [state.dashboard?.trend, state.currentOverviewRun, state.dailyRuns, state.overviewRunIndex]
  );

  // Resolve whether the UI is currently rendering dark. Used by the
  // topbar's moon/sun toggle so the icon reflects what's on-screen,
  // not just the saved mode preference.
  const effectiveDark = useEffectiveDark(state.settings.themeMode);
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

  const contentProps = {
    dashboardData: {
      selectedProject: state.selectedProject, selectedRun: state.selectedRun, projects: state.projects,
      projectsLoaded: state.projectsLoaded,
      dashboard: state.dashboard, accumulated: state.accumulated, latestAccumulated: state.latestAccumulated, loading: state.loading, isFetching: state.isFetching, error: state.error,
      availableRuns: state.availableRuns, dailyRuns: state.dailyRuns, overviewRunIndex: state.overviewRunIndex,
      selectedDisplayName: state.selectedDisplayName,
    },
    navigation: {
      selectedProject: state.selectedProject, selectedRun: state.selectedRun, projects: state.projects,
      projectsLoaded: state.projectsLoaded,
      loadProjects: state.loadProjects,
      handleNavigate: state.handleNavigate, handleRunSelect: state.handleRunSelect,
      handleProjectChange: state.handleProjectChange, navTab, navStackLength: navStack.length,
      handleDeleteProject: state.handleDeleteProject, handleExportProject: state.handleExportProject, handleRelocateProject: state.handleRelocateProject,
      historySelectedRun: state.historySelectedRun, setHistorySelectedRun: state.setHistorySelectedRun,
      currentOverviewRun: state.currentOverviewRun, handleRunPrev: state.handleRunPrev, handleRunNext: state.handleRunNext, handleRunLatest: state.handleRunLatest,
      prefetchHandlers: state.prefetchHandlers,
      onAddProject: () => {
        if (isEvaluating) {
          showToast('An evaluation is in progress. Cancel it before adding a project.');
          return;
        }
        setWizardEntry({ startStep: 'repo-scan', isFirstProject: state.projects.length === 0 });
      },
      onTakeTour: () => {
        if (isEvaluating) {
          showToast('An evaluation is in progress. Cancel it before starting the tour.');
          return;
        }
        setWizardEntry({ startStep: 'welcome', isFirstProject: true });
      },
      onResumeSetup: (projectId) => {
        if (isEvaluating) {
          showToast('An evaluation is in progress. Cancel it before resuming setup.');
          return;
        }
        setWizardEntry({
          startStep: 'provider',
          isFirstProject: false,
          presetProjectId: projectId,
        });
      },
      isEvaluating,
    },
    evaluation: state.evalLifecycle,
    serverHealth: { connected: state.serverConnected, setConnected: state.setServerConnected },
    settings: state.settings,
    refreshDashboard: state.refreshDashboard,
    dismissFinding,
  };

  // Resolve the project's friendly name. Until the /api/projects response
  // has populated the projects array, selectedDisplayName falls back to the
  // raw project id (a UUID) — we explicitly filter that case out so the
  // sidebar and topbar show nothing rather than flashing the UUID.
  const resolvedDisplayName =
    selectedProjectInfo?.displayName
    || selectedProjectInfo?.name
    || (state.selectedDisplayName && state.selectedDisplayName !== state.selectedProject
          ? state.selectedDisplayName
          : null);

  return (
    <>
      <EvalLogProvider>
        <ServerLogProvider>
          <OllamaLogProvider>
            <AppShell
          sidebar={
            <Sidebar
              activeTab={activeTab}
              onNavTab={navTab}
              hasEvaluations={state.projects.length > 0}
              showProjectTabs={hasCurrentProjectRuns}
              projectInfo={{
                displayName: resolvedDisplayName,
                meta: state.headerMeta,
              }}
              version={APP_VERSION}
              violationsCount={filteredAccumulated?.summary?.totalViolations ?? state.accumulated?.summary?.totalViolations ?? null}
              historyCount={filteredTrend.length || state.dashboard?.trend?.length || null}
              lastEvalAt={state.accumulated?.summary?.lastEvaluatedAt || state.accumulated?.summary?.createdAt || null}
              serverConnected={state.serverConnected}
              isPinned={sidebarPinned}
              onPinChange={setSidebarPinned}
              mobileExtras={(
                <div className="sidebar-mobile-extras__grid">
                  {(sidebarProvider || sidebarModel) && (
                    <div className="sidebar-status-row">
                      <span className="sidebar-status-label">Provider</span>
                      <span className="sidebar-status-value">
                        {sidebarProvider || '\u2014'}
                        {sidebarModel && <>&nbsp;·&nbsp;<span style={{ opacity: 0.7 }}>{sidebarModel}</span></>}
                      </span>
                    </div>
                  )}
                </div>
              )}
            />
          }
          header={
            <TopBar
              projectName={resolvedDisplayName}
              activeTab={activeTab}
              serverConnected={state.serverConnected}
              serverUrl={state.serverHealth?.url || null}
              provider={sidebarProvider}
              model={sidebarModel}
              onEvaluate={state.projects?.length > 0 ? (() => navTab('evaluate')) : null}
              evaluating={state.evalLifecycle?.job?.status === 'running'}
              onProviderClick={() => navTab('settings')}
              onMenuToggle={() => setSidebarPinned((v) => !v)}
              breadcrumb={
                <NavBreadcrumb
                  stack={navStack}
                  onBack={navPop}
                  onGoTo={navGoTo}
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
            <Suspense fallback={<LoadingScreen />}>
              <div className="tab-fade" key={activeTab}>
                <MainContent activePage={activePage} props={contentProps} />
              </div>
              {wizardEntry && (
                <OnboardingWizard
                  entry={wizardEntry}
                  onClose={({ saved, projectId }) => {
                    setWizardEntry(null);
                    if (saved && projectId) {
                      state.refreshDashboard?.();
                    }
                  }}
                  onLaunch={({ projectId, repo, scopePath, branch, provider, standardIds, totalTimeLimitS }) => {
                    setWizardEntry(null);
                    const payload = {
                      repo: repo || projectId,
                      dimensions: standardIds,
                    };
                    if (scopePath) payload.scopePath = scopePath;
                    if (branch) payload.branch = branch;
                    if (provider?.id) payload.aiCmd = provider.id;
                    if (provider?.model) payload.aiModel = provider.model;
                    if (totalTimeLimitS) payload.timeLimit = totalTimeLimitS;
                    state.evalLifecycle.handleStartEvaluation(payload);
                    navTab('evaluate');
                  }}
                />
              )}
            </Suspense>
          }
            />
          </OllamaLogProvider>
        </ServerLogProvider>
      </EvalLogProvider>
    {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
    </>
  );
}
