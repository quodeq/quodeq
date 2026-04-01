import { useState, useMemo } from 'react';
import { useDashboard } from './features/dashboard/hooks/useDashboard.js';
import { buildDailyRuns } from './utils/dailyGrouping.js';
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
import ServerDisconnectedOverlay from './components/ServerDisconnectedOverlay.jsx';
import LoadingScreen from './components/LoadingScreen.jsx';
import Sidebar from './components/Sidebar.jsx';
import ProjectHeader from './components/ProjectHeader.jsx';
import { useServerHealth } from './hooks/useServerHealth.js';
import { useNavStack } from './hooks/useNavStack.js';
import { useRunNavigator } from './hooks/useRunNavigator.js';
import { useProjectState } from './hooks/useProjectState.js';
import { useAppSettings } from './hooks/useAppSettings.js';
import { useEvaluationLifecycle } from './hooks/useEvaluationLifecycle.js';
import { useProjectActions } from './hooks/useProjectActions.js';
import { useVisibleRuns } from './hooks/useVisibleRuns.js';


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

const ROUTE_RENDERERS = {
  overview: (params, props) => <DashboardPage data={props.dashboardData} callbacks={{ onNavigate: props.navigation.handleNavigate, onRunSelect: props.navigation.handleRunSelect }} runMode={false} />,
  violations: (params, props) => {
    const acc = props.dashboardData.latestAccumulated || props.dashboardData.accumulated;
    const dims = acc?.dimensions || [];
    const nav = props.navigation.handleNavigate;
    return (
      <ViolationsPage
        data={{ accumulated: acc, accumulatedDimensions: dims }}
        callbacks={{
          onDimensionClick: (dim) => nav('explorer', { dimension: dim.dimension, runId: dim.fromRunId, dateLabel: dim.fromDateLabel, sourceTab: 'violations' }),
          onFileClick: (fileObj) => nav('file', { file: fileObj, sourceTab: 'violations' }),
          onPrincipleClick: (principleObj) => nav('principle', { principle: principleObj, sourceTab: 'violations' }),
        }}
      />
    );
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
  explorer: (params, props) => <ExplorerPage project={props.navigation.selectedProject} dimension={params.dimension} runId={params.runId} dateLabel={params.dateLabel} onNavigate={props.navigation.handleNavigate} />,
  evaluate: (params, props) => <EvaluateCase serverHealth={props.serverHealth} evaluation={props.evaluation} selectedProject={props.navigation.selectedProject} />,
  file: (params) => <FileDetailPage file={params.file} />,
  principle: (params) => <PrincipleDetailPage principle={params.principle} />,
  evalprinciple: (params) => <EvalPrincipleDetailPage evalPrincipal={params.evalPrincipal} />,
  'eval-principle-detail': (params) => <EvalPrincipleDetailPage evalPrincipal={params.evalPrincipal} />,
  settings: (params, props) => <SettingsCase settings={props.settings} analysisPower={props.evaluation.analysisPower} setAnalysisPower={props.evaluation.setAnalysisPower} persistAnalysisPower={props.evaluation.persistAnalysisPower} />,
  projects: (params, props) => <ProjectsPage projects={props.navigation.projects} selectedProject={props.navigation.selectedProject} actions={{ onSelect: (id) => { props.navigation.handleProjectChange(id); props.navigation.navTab('overview'); }, onDelete: props.navigation.handleDeleteProject, onExport: props.navigation.handleExportProject, onRelocate: props.navigation.handleRelocateProject }} />,
  standards: () => <StandardsPage />,
};

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

function computeHeaderMeta(accumulated, dashboard, selectedProject, projects) {
  const accDims = accumulated?.dimensions || [];
  if (accDims.length === 0) return null;
  const discipline = accDims.find((d) => d.discipline)?.discipline ?? null;
  const repository = accDims.find((d) => d.repository)?.repository ?? null;
  const runDims = dashboard?.dimensions || [];
  const totalFiles = runDims.find((d) => d.sourceFileCount)?.sourceFileCount ?? null;
  const project = projects.find((p) => p.id === selectedProject);
  const languageStats = project?.languageStats ?? null;
  return { discipline, repository, totalFiles, languageStats };
}

function computeProjectDisplay(selectedProject, projects) {
  if (!selectedProject || !projects.length) return { selectedDisplayName: selectedProject, selectedProjectParent: null, selectedProjectParentId: null };
  const data = projects.find((p) => (p.id || p.name || p) === selectedProject);
  const parentRef = data?.parent || null;
  const parentData = parentRef ? projects.find((p) => (p.id || p.name || p) === parentRef) : null;
  const parentId = parentData ? (parentData.id || parentData.name || parentRef) : null;
  return {
    selectedDisplayName: data?.displayName || data?.name || selectedProject,
    selectedProjectParent: parentData?.displayName || parentData?.name || parentRef,
    selectedProjectParentId: parentId,
  };
}

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

function useProjects({ onNoProjects }) {
  const projectState = useProjectState({ onNoProjects });
  const projectActions = useProjectActions({
    projects: projectState.projects,
    selectedProject: projectState.selectedProject,
    handleProjectChange: projectState.handleProjectChange,
    loadProjects: projectState.loadProjects,
  });
  return { ...projectState, ...projectActions };
}

function useAppNavigation() {
  const [serverConnected, setServerConnected] = useServerHealth();
  const { navStack, activePage, navPush, navPop, navGoTo, navReset, navTab } = useNavStack();
  const projectBundle = useProjects({ onNoProjects: () => navTab('evaluate') });
  const { selectedRun, setSelectedRun, handleRunChange } = projectBundle;
  const [historySelectedRun, setHistorySelectedRun] = useState('latest');
  function handleNavigate(page, params = {}) {
    if (page === 'run' && params.runId) setSelectedRun(params.runId);
    if (page === 'history-run' && params.runId) setHistorySelectedRun(params.runId);
    navPush({ page, ...params });
  }
  return { serverConnected, setServerConnected, navStack, activePage, navPush, navPop, navGoTo, navReset, navTab, projectBundle, handleNavigate, handleRunChange, historySelectedRun, setHistorySelectedRun };
}

function useAppState() {
  const nav = useAppNavigation();
  const { serverConnected, setServerConnected, navStack, activePage, navPop, navGoTo, navReset, navTab, projectBundle, handleNavigate, handleRunChange, historySelectedRun, setHistorySelectedRun } = nav;
  const { projects, setProjects, selectedProject, selectedRun, setSelectedRun, loadProjects, handleProjectChange, selectProjectAndRun, handleDeleteProject, handleExportProject, handleRelocateProject } = projectBundle;
  const settings = useAppSettings();
  const effectiveRun = activePage.page === 'history-run' ? historySelectedRun : selectedRun;
  const { dashboard, accumulated, latestAccumulated, loading, error, availableRuns } = useDashboard({ selectedProject, selectedRun: effectiveRun });
  const dailyRuns = useMemo(() => buildDailyRuns(availableRuns, dashboard?.trend || []), [availableRuns, dashboard]);
  const visibleDailyRuns = useVisibleRuns(dailyRuns, dashboard, activePage.page, setSelectedRun);
  const { overviewRunIndex, currentOverviewRun, handleRunPrev, handleRunNext, handleRunLatest, handleRunView, handleRunSelect } = useRunNavigator({ selectedRun, availableRuns: visibleDailyRuns, onRunChange: handleRunChange, onNavigate: handleNavigate });
  const { headerMeta, selectedDisplayName, selectedProjectParent, selectedProjectParentId } = useMemo(() => {
    const meta = computeHeaderMeta(accumulated, dashboard, selectedProject, projects);
    const display = computeProjectDisplay(selectedProject, projects);
    return { headerMeta: meta, ...display };
  }, [accumulated, dashboard, selectedProject, projects]);
  const evalLifecycle = useEvaluationLifecycle({ settings, navigation: { navTab, navReset }, projects: { loadProjects, setProjects, selectProjectAndRun } });
  const knownTabs = ['overview', 'violations', 'history', 'projects', 'evaluate', 'standards', 'settings'];
  const activeTab = knownTabs.includes(activePage.page) ? activePage.page
    : activePage.sourceTab && knownTabs.includes(activePage.sourceTab) ? activePage.sourceTab
    : activePage.page === 'history-run' ? 'history'
    : 'overview';
  const showProjectHeader = ['overview'].includes(activeTab) && projects.length > 0 && !!selectedProject;
  const showRunNav = showProjectHeader && visibleDailyRuns.length > 0 && navStack.length === 1;

  return {
    serverConnected, setServerConnected, navStack, activePage, navPop, navGoTo, navTab,
    projects, selectedProject, selectedRun, handleProjectChange, handleNavigate,
    handleDeleteProject, handleExportProject, handleRelocateProject,
    dashboard, accumulated, latestAccumulated, loading, error, availableRuns, dailyRuns: visibleDailyRuns, overviewRunIndex,
    currentOverviewRun, handleRunPrev, handleRunNext, handleRunLatest, handleRunView, handleRunSelect,
    headerMeta, selectedDisplayName, selectedProjectParent, selectedProjectParentId,
    historySelectedRun, setHistorySelectedRun,
    evalLifecycle, settings, activeTab, showProjectHeader, showRunNav,
  };
}

function formatDayLabel(trend, currentOverviewRun, dailyRuns, overviewRunIndex) {
  const entry = (trend || []).find((r) => r.runId === currentOverviewRun);
  if (entry?.dateISO) {
    try {
      return new Date(entry.dateISO).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
    } catch { return entry.dateISO; }
  }
  return dailyRuns[overviewRunIndex]?.dateLabel || currentOverviewRun;
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
      dashboard: state.dashboard, accumulated: state.accumulated, latestAccumulated: state.latestAccumulated, loading: state.loading, error: state.error,
      availableRuns: state.availableRuns, dailyRuns: state.dailyRuns, overviewRunIndex: state.overviewRunIndex,
    },
    navigation: {
      selectedProject: state.selectedProject, selectedRun: state.selectedRun, projects: state.projects,
      handleNavigate: state.handleNavigate, handleRunSelect: state.handleRunSelect,
      handleProjectChange: state.handleProjectChange, navTab,
      handleDeleteProject: state.handleDeleteProject, handleExportProject: state.handleExportProject, handleRelocateProject: state.handleRelocateProject,
      historySelectedRun: state.historySelectedRun, setHistorySelectedRun: state.setHistorySelectedRun,
      currentOverviewRun: state.currentOverviewRun, handleRunPrev: state.handleRunPrev, handleRunNext: state.handleRunNext, handleRunLatest: state.handleRunLatest,
    },
    evaluation: state.evalLifecycle,
    serverHealth: { connected: state.serverConnected, setConnected: state.setServerConnected },
    settings: state.settings,
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
      content={<MainContent activePage={activePage} props={contentProps} />}
    />
  );
}
