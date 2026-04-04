import { useMemo } from 'react';
import DashboardPage from './features/dashboard/components/DashboardPage.jsx';
import NavBreadcrumb from './features/explorer/components/NavBreadcrumb.jsx';
import ExplorerPage from './features/explorer/components/ExplorerPage.jsx';
import FileDetailPage from './features/explorer/components/FileDetailPage.jsx';
import PrincipleDetailPage from './features/explorer/components/PrincipleDetailPage.jsx';
import EvalPrincipleDetailPage from './features/explorer/components/EvalPrincipleDetailPage.jsx';
import ProjectsPage from './features/dashboard/components/ProjectsPage.jsx';
import HistoryPage from './features/history/components/HistoryPage.jsx';
import EvaluateScreen from './features/evaluation/components/EvaluateScreen.jsx';
import SettingsPage from './features/settings/components/SettingsPage.jsx';
import StandardsPage from './features/standards/StandardsPage.jsx';
import ViolationsPage from './features/violations/components/ViolationsPage.jsx';
import MapPage from './features/map/components/MapPage.jsx';
import ServerDisconnectedOverlay from './components/ServerDisconnectedOverlay.jsx';
import { dismissFinding } from './api/index.js';
import LoadingScreen from './components/LoadingScreen.jsx';
import Sidebar from './components/Sidebar.jsx';
import ProjectHeader from './components/ProjectHeader.jsx';
import { useAppState, formatDayLabel, KNOWN_TABS } from './hooks/useAppState.js';


/**
 * @param {{ serverHealth: Object, evaluation: Object, selectedProject: string }} props
 * @returns {JSX.Element}
 */
function EvaluateCase({ serverHealth, evaluation, selectedProject }) {
  const { connected, setConnected } = serverHealth;
  const { job, jobError, liveViolations, analysisPower, setAnalysisPower, persistAnalysisPower, handleStartEvaluation, handleEvalDismiss, cancelEvaluation } = evaluation;
  return (
    <>
      {!connected && <ServerDisconnectedOverlay onReconnect={() => setConnected(true)} />}
      <EvaluateScreen
        evaluation={{ job, jobError, liveViolations }}
        context={{ selectedProject, analysisPower, onAnalysisPowerChange: setAnalysisPower, onPersistPower: persistAnalysisPower }}
        actions={{ onStart: handleStartEvaluation, onDismiss: handleEvalDismiss, onCancel: cancelEvaluation }}
      />
    </>
  );
}

/**
 * @param {{ settings: Object, analysisPower: string, setAnalysisPower: Function, persistAnalysisPower: Function }} props
 * @returns {JSX.Element}
 */
function SettingsCase({ settings, analysisPower, setAnalysisPower, persistAnalysisPower }) {
  return (
    <SettingsPage
      theme={{ mode: settings.themeMode, family: settings.themeFamily, onApplyMode: settings.applyMode, onApplyFamily: settings.applyFamily }}
      models={{
        aiCmd: settings.aiCmd, onApplyAiCmd: settings.applyAiCmd,
        aiModel: settings.aiModel, onAiModelChange: settings.setAiModel,
        fast: settings.modelFast, onFastChange: settings.setModelFast,
        balanced: settings.modelBalanced, onBalancedChange: settings.setModelBalanced,
        thorough: settings.modelThorough, onThoroughChange: settings.setModelThorough,
      }}
      analysis={{ power: analysisPower, onPowerChange: setAnalysisPower, onPersist: persistAnalysisPower }}
      verification={{ enabled: settings.verifyFindings, onApply: settings.applyVerifyFindings }}
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
  return (
    <EvalPrincipleDetailPage
      evalPrincipal={params.evalPrincipal}
      onDismiss={(v) => {
        dismissFinding(props.navigation.selectedProject, buildDismissPayload(v, params.evalPrincipal?.dimension))
          .then(() => props.refreshDashboard?.())
          .catch((e) => console.error('[Dismiss] failed:', e));
      }}
    />
  );
}

const ROUTE_RENDERERS = {
  overview: (params, props) => <DashboardPage data={props.dashboardData} callbacks={{ onNavigate: props.navigation.handleNavigate, onRunSelect: props.navigation.handleRunSelect }} runMode={false} />,
  violations: (params, props) => {
    const acc = props.dashboardData.latestAccumulated || props.dashboardData.accumulated;
    const dims = acc?.dimensions || [];
    const nav = props.navigation.handleNavigate;
    return (
      <ViolationsPage
        data={{ accumulated: acc, accumulatedDimensions: dims, selectedProject: props.navigation.selectedProject }}
        callbacks={{
          onDimensionClick: (dim) => nav('explorer', { dimension: dim.dimension, runId: dim.fromRunId, dateLabel: dim.fromDateLabel, sourceTab: 'violations' }),
          onFileClick: (fileObj) => nav('file', { file: fileObj, sourceTab: 'violations' }),
          onPrincipleClick: (principleObj) => nav('principle', { principle: principleObj, sourceTab: 'violations' }),
          onRefresh: props.refreshDashboard,
        }}
        isDirectNav={props.navigation.navStackLength === 1}
      />
    );
  },
  map: (params, props) => {
    const acc = props.dashboardData.latestAccumulated || props.dashboardData.accumulated;
    const isDirectNav = props.navigation.navStackLength === 1;
    return <MapPage data={{ accumulated: acc, dashboard: props.dashboardData.dashboard }} callbacks={{ onNavigate: props.navigation.handleNavigate, onRefresh: props.refreshDashboard }} isDirectNav={isDirectNav} tabKey={params._tabKey || 0} />;
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
          onDimensionClick: (dim) => props.navigation.handleNavigate('explorer', { dimension: dim.dimension, runId: dim.fromRunId, dateLabel: dim.fromDateLabel }),
          onNavigate: props.navigation.handleNavigate,
          onRunChange: props.navigation.setHistorySelectedRun,
        }}
      />
    );
  },
  'history-run': (params, props) => <DashboardPage data={props.dashboardData} callbacks={{ onNavigate: props.navigation.handleNavigate }} runMode={true} />,
  explorer: (params, props) => <ExplorerPage project={props.navigation.selectedProject} dimension={params.dimension} runId={params.runId} dateLabel={params.dateLabel} onNavigate={props.navigation.handleNavigate} refreshSignal={props.dashboardData.dashboard} />,
  evaluate: (params, props) => <EvaluateCase serverHealth={props.serverHealth} evaluation={props.evaluation} selectedProject={props.navigation.selectedProject} />,
  file: (params) => <FileDetailPage file={params.file} />,
  principle: (params) => <PrincipleDetailPage principle={params.principle} />,
  evalprinciple: renderEvalPrincipleDetail,
  'eval-principle-detail': renderEvalPrincipleDetail,
  settings: (params, props) => <SettingsCase settings={props.settings} analysisPower={props.evaluation.analysisPower} setAnalysisPower={props.evaluation.setAnalysisPower} persistAnalysisPower={props.evaluation.persistAnalysisPower} />,
  projects: (params, props) => <ProjectsPage projects={props.navigation.projects} selectedProject={props.navigation.selectedProject} actions={{ onSelect: (id) => { props.navigation.handleProjectChange(id); props.navigation.navTab('overview'); }, onDelete: props.navigation.handleDeleteProject, onExport: props.navigation.handleExportProject, onRelocate: props.navigation.handleRelocateProject }} />,
  standards: () => <StandardsPage />,
};

/**
 * @param {{ activePage: { page: string }, props: Object }} params
 * @returns {JSX.Element|null}
 */
function MainContent({ activePage, props }) {
  const { page, ...params } = activePage;
  const noProjectTabs = ['evaluate', 'standards', 'settings'];
  if (!noProjectTabs.includes(page)) {
    const projects = props.navigation?.projects;
    if (!projects || projects.length === 0) {
      if (props.dashboardData?.loading) return <LoadingScreen />;
      return <section className="empty-state"><h2>No analyzed projects yet</h2><p>Run an evaluation to get started.</p></section>;
    }
  }
  const renderer = ROUTE_RENDERERS[page];
  if (renderer) return renderer(params, props);
  return null;
}

/**
 * @param {{ sidebar: JSX.Element, header: JSX.Element|null, breadcrumb: JSX.Element|null, content: JSX.Element }} props
 * @returns {JSX.Element}
 */
function AppShell({ sidebar, header, breadcrumb, content }) {
  return (
    <div className="app-shell">
      {sidebar}
      <main className="dashboard">
        {header}
        {breadcrumb}
        {content}
      </main>
    </div>
  );
}

export default function App() {
  const state = useAppState();
  const { activePage, navStack, navPop, navGoTo, navTab, activeTab } = state;

  const currentDayLabel = useMemo(
    () => formatDayLabel(state.dashboard?.trend, state.currentOverviewRun, state.dailyRuns, state.overviewRunIndex),
    [state.dashboard?.trend, state.currentOverviewRun, state.dailyRuns, state.overviewRunIndex]
  );

  const contentProps = {
    dashboardData: {
      selectedProject: state.selectedProject, selectedRun: state.selectedRun, projects: state.projects,
      dashboard: state.dashboard, accumulated: state.accumulated, latestAccumulated: state.latestAccumulated, rescoreLookup: state.rescoreLookup, loading: state.loading, error: state.error,
      availableRuns: state.availableRuns, dailyRuns: state.dailyRuns, overviewRunIndex: state.overviewRunIndex,
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
  };

  return (
    <AppShell
      sidebar={<Sidebar activeTab={activeTab} onNavTab={navTab} />}
      header={state.showProjectHeader ? (
        <ProjectHeader
          project={{ displayName: state.selectedDisplayName, parent: state.selectedProjectParent, parentId: state.selectedProjectParentId, meta: state.headerMeta }}
          navigation={{
            onProjectChange: state.handleProjectChange, showRunNav: state.showRunNav,
            runNavProps: {
              currentOverviewRun: state.currentOverviewRun, overviewRunIndex: state.overviewRunIndex, availableRuns: state.dailyRuns,
              currentDayLabel,
              onRunPrev: state.handleRunPrev, onRunNext: state.handleRunNext, onRunLatest: state.handleRunLatest,
            },
          }}
        />
      ) : null}
      breadcrumb={navStack.length > 1 ? <NavBreadcrumb stack={navStack} onBack={navPop} onGoTo={navGoTo} /> : null}
      content={<div className="tab-fade" key={activeTab}><MainContent activePage={activePage} props={contentProps} /></div>}
    />
  );
}
