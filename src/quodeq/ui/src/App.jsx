import { useMemo, useState } from 'react';
import DashboardPage from './features/dashboard/components/DashboardPage.jsx';
import NavBreadcrumb, { labelFor as navLabelFor } from './features/explorer/components/NavBreadcrumb.jsx';
import ExplorerPage from './features/explorer/components/ExplorerPage.jsx';
import FileDetailPage from './features/explorer/components/FileDetailPage.jsx';
import PrincipleDetailPage from './features/explorer/components/PrincipleDetailPage.jsx';
import FindingDetailPage from './features/explorer/components/FindingDetailPage.jsx';
import ProjectsPage from './features/dashboard/components/ProjectsPage.jsx';
import HistoryPage from './features/history/components/HistoryPage.jsx';
import EvaluateScreen from './features/evaluation/components/EvaluateScreen.jsx';
import SettingsPage from './features/settings/components/SettingsPage.jsx';
import StandardsPage from './features/standards/StandardsPage.jsx';
import ViolationsPage from './features/violations/components/ViolationsPage.jsx';
import MapPage from './features/map/components/MapPage.jsx';
import HelpPage from './features/help/components/HelpPage.jsx';
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

const NO_PROJECT_TABS = ['evaluate', 'standards', 'settings', 'help'];

/**
 * @param {{ serverHealth: Object, evaluation: Object, selectedProject: string }} props
 * @returns {JSX.Element}
 */
function EvaluateCase({ serverHealth, evaluation, selectedProject, projects }) {
  const { connected, setConnected } = serverHealth;
  const { job, jobError, liveViolations, handleStartEvaluation, handleEvalDismiss, cancelEvaluation } = evaluation;
  const projectInfo = projects?.find(p => (p.id || p.name) === selectedProject) || null;
  return (
    <>
      {!connected && <ServerDisconnectedOverlay onReconnect={() => setConnected(true)} />}
      <EvaluateScreen
        evaluation={{ job, jobError, liveViolations }}
        context={{ selectedProject, projectInfo }}
        actions={{ onStart: handleStartEvaluation, onDismiss: handleEvalDismiss, onCancel: cancelEvaluation }}
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
      data={{ accumulated: acc, accumulatedDimensions: dims, selectedProject: props.navigation.selectedProject }}
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
      }}
      isDirectNav={props.navigation.navStackLength === 1}
      tabKey={params._tabKey || 0}
    />
  );
}

const ROUTE_RENDERERS = {
  overview: (params, props) => <DashboardPage data={props.dashboardData} callbacks={{ onNavigate: props.navigation.handleNavigate, onRunSelect: props.navigation.handleRunSelect }} runMode={false} />,
  violations: (params, props) => <ViolationsRoute params={params} props={props} />,
  map: (params, props) => {
    const acc = props.dashboardData.latestAccumulated || props.dashboardData.accumulated;
    const isDirectNav = props.navigation.navStackLength === 1;
    return <MapPage data={{ accumulated: acc, dashboard: props.dashboardData.dashboard, projectName: props.dashboardData.selectedDisplayName }} callbacks={{ onNavigate: props.navigation.handleNavigate, onRefresh: props.refreshDashboard }} isDirectNav={isDirectNav} tabKey={params._tabKey || 0} />;
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
        }}
        projectInfo={props.navigation.projects?.find((p) => (p.id || p.name) === props.navigation.selectedProject) || null}
      />
    );
  },
  'history-run': (params, props) => <DashboardPage data={props.dashboardData} callbacks={{ onNavigate: props.navigation.handleNavigate }} runMode={true} />,
  explorer: (params, props) => <ExplorerPage project={params.fromProject || props.navigation.selectedProject} dimension={params.dimension} runId={params.runId} dateLabel={params.dateLabel} severityFilter={params.severity} onNavigate={props.navigation.handleNavigate} refreshSignal={props.dashboardData.dashboard} />,
  evaluate: (params, props) => <EvaluateCase serverHealth={props.serverHealth} evaluation={props.evaluation} selectedProject={props.navigation.selectedProject} projects={props.navigation.projects} />,
  file: (params) => <FileDetailPage file={params.file} />,
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
  projects: (params, props) => <ProjectsPage projects={props.navigation.projects} selectedProject={props.navigation.selectedProject} actions={{ onSelect: (id) => { props.navigation.handleProjectChange(id); props.navigation.navTab('overview'); }, onDelete: props.navigation.handleDeleteProject, onExport: props.navigation.handleExportProject, onRelocate: props.navigation.handleRelocateProject }} />,
  standards: () => <StandardsPage />,
  help: () => <HelpPage />,
};

/**
 * @param {{ activePage: { page: string }, props: Object }} params
 * @returns {JSX.Element|null}
 */
function MainContent({ activePage, props }) {
  const { page, ...params } = activePage;
  if (!NO_PROJECT_TABS.includes(page)) {
    const projects = props.navigation?.projects;
    if (!projects || projects.length === 0) {
      if (!props.navigation?.projectsLoaded) return <LoadingScreen />;
      return <section className="empty-state"><h2>No analyzed projects yet</h2><p>Run an evaluation to get started.</p></section>;
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
      </div>
    </div>
  );
}

export default function App() {
  const { dismissFinding } = useApi();
  const state = useAppState();
  const APP_VERSION = '1.0.6';
  const selectedProjectInfo = state.projects?.find((p) => (p.id || p.name) === state.selectedProject) || null;
  const [sidebarPinned, setSidebarPinned] = useState(false);
  const sidebarProvider = (typeof localStorage !== 'undefined' && localStorage.getItem(ACTIVE_PROVIDER_KEY)) || null;
  const sidebarModel = sidebarProvider && typeof localStorage !== 'undefined'
    ? localStorage.getItem(providerKey(sidebarProvider, 'model'))
    : null;
  const { activePage, navStack, navPop, navGoTo, navTab, activeTab } = state;

  const currentDayLabel = useMemo(
    () => formatDayLabel(state.dashboard?.trend, state.currentOverviewRun, state.dailyRuns, state.overviewRunIndex),
    [state.dashboard?.trend, state.currentOverviewRun, state.dailyRuns, state.overviewRunIndex]
  );

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
      dashboard: state.dashboard, accumulated: state.accumulated, latestAccumulated: state.latestAccumulated, loading: state.loading, error: state.error,
      availableRuns: state.availableRuns, dailyRuns: state.dailyRuns, overviewRunIndex: state.overviewRunIndex,
      selectedDisplayName: state.selectedDisplayName,
    },
    navigation: {
      selectedProject: state.selectedProject, selectedRun: state.selectedRun, projects: state.projects,
      handleNavigate: state.handleNavigate, handleRunSelect: state.handleRunSelect,
      handleProjectChange: state.handleProjectChange, navTab, navStackLength: navStack.length,
      handleDeleteProject: state.handleDeleteProject, handleExportProject: state.handleExportProject, handleRelocateProject: state.handleRelocateProject,
      historySelectedRun: state.historySelectedRun, setHistorySelectedRun: state.setHistorySelectedRun,
      currentOverviewRun: state.currentOverviewRun, handleRunPrev: state.handleRunPrev, handleRunNext: state.handleRunNext, handleRunLatest: state.handleRunLatest,
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
    <AppShell
      sidebar={
        <Sidebar
          activeTab={activeTab}
          onNavTab={navTab}
          hasEvaluations={state.projects.length > 0}
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
          onReport={null}
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
        />
      }
      content={<div className="tab-fade" key={activeTab}><MainContent activePage={activePage} props={contentProps} /></div>}
    />
  );
}
