import { useMemo } from 'react';
import { useDashboard } from './features/dashboard/hooks/useDashboard.js';
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
import ServerDisconnectedOverlay from './components/ServerDisconnectedOverlay.jsx';
import Sidebar from './components/Sidebar.jsx';
import ProjectHeader from './components/ProjectHeader.jsx';
import { useServerHealth } from './hooks/useServerHealth.js';
import { useNavStack } from './hooks/useNavStack.js';
import { useRunNavigator } from './hooks/useRunNavigator.js';
import { useProjectState } from './hooks/useProjectState.js';
import { useAppSettings } from './hooks/useAppSettings.js';
import { useEvaluationLifecycle } from './hooks/useEvaluationLifecycle.js';
import { useProjectActions } from './hooks/useProjectActions.js';


function EvaluateCase({ serverHealth, evaluation, selectedProject }) {
  const { connected, setConnected } = serverHealth;
  const { job, jobError, liveViolations, analysisPower, setAnalysisPower, handleStartEvaluation, handleEvalDismiss, cancelEvaluation } = evaluation;
  return (
    <>
      {!connected && <ServerDisconnectedOverlay onReconnect={() => setConnected(true)} />}
      <EvaluateScreen
        evaluation={{ job, jobError, liveViolations }}
        context={{ selectedProject, analysisPower, onAnalysisPowerChange: setAnalysisPower }}
        actions={{ onStart: handleStartEvaluation, onDismiss: handleEvalDismiss, onCancel: cancelEvaluation }}
      />
    </>
  );
}

function SettingsCase({ settings, analysisPower, setAnalysisPower }) {
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
      analysis={{ power: analysisPower, onPowerChange: setAnalysisPower }}
      verification={{ enabled: settings.verifyFindings, onApply: settings.applyVerifyFindings }}
    />
  );
}

const ROUTE_RENDERERS = {
  overview: (params, props) => <DashboardPage data={props.dashboardData} callbacks={{ onNavigate: props.navigation.handleNavigate, onRunSelect: props.navigation.handleRunSelect }} runMode={false} />,
  run: (params, props) => <DashboardPage data={props.dashboardData} callbacks={{ onNavigate: props.navigation.handleNavigate }} runMode={true} />,
  history: (params, props) => {
    const trend = props.dashboardData.dashboard?.trend || [];
    const runs = props.dashboardData.availableRuns || [];
    const idx = props.dashboardData.overviewRunIndex || 0;
    return (
      <HistoryPage
        trend={trend}
        selectedRunId={props.dashboardData.selectedRun}
        selectedRunScore={props.dashboardData.accumulated?.summary?.numericAverage}
        runNav={runs.length > 0 ? {
          currentRun: props.navigation.currentOverviewRun,
          isLatest: idx === 0,
          isOldest: idx >= runs.length - 1,
          onPrev: props.navigation.handleRunPrev,
          onNext: props.navigation.handleRunNext,
          onLatest: props.navigation.handleRunLatest,
        } : null}
        onRunClick={(runId, dateLabel) => props.navigation.handleNavigate('history-run', { runId, dateLabel })}
        onBarClick={props.navigation.handleRunSelect}
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
  settings: (params, props) => <SettingsCase settings={props.settings} analysisPower={props.evaluation.analysisPower} setAnalysisPower={props.evaluation.setAnalysisPower} />,
  projects: (params, props) => <ProjectsPage projects={props.navigation.projects} selectedProject={props.navigation.selectedProject} actions={{ onSelect: (id) => { props.navigation.handleProjectChange(id); props.navigation.navTab('overview'); }, onDelete: props.navigation.handleDeleteProject, onExport: props.navigation.handleExportProject, onRelocate: props.navigation.handleRelocateProject }} />,
};

function MainContent({ activePage, props }) {
  const { page, ...params } = activePage;
  const renderer = ROUTE_RENDERERS[page];
  if (renderer) return renderer(params, props);
  return <div className="empty-state"><p>Page not found: {page}</p></div>;
}

function computeHeaderMeta(accumulated, dashboard) {
  const accDims = accumulated?.dimensions || [];
  if (accDims.length === 0) return null;
  const discipline = accDims.find((d) => d.discipline)?.discipline ?? null;
  const repository = accDims.find((d) => d.repository)?.repository ?? null;
  const runDims = dashboard?.dimensions || [];
  const totalFiles = runDims.find((d) => d.sourceFileCount)?.sourceFileCount ?? null;
  return { discipline, repository, totalFiles };
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

function useAppState() {
  const [serverConnected, setServerConnected] = useServerHealth();
  const { navStack, activePage, navPush, navPop, navGoTo, navReset, navTab } = useNavStack();
  const projectBundle = useProjects({ onNoProjects: () => navTab('evaluate') });
  const { projects, setProjects, selectedProject, selectedRun, setSelectedRun, loadProjects, handleProjectChange, handleRunChange, selectProjectAndRun, handleDeleteProject, handleExportProject, handleRelocateProject } = projectBundle;
  const settings = useAppSettings();
  function handleNavigate(page, params = {}) { if ((page === 'run' || page === 'history-run') && params.runId) setSelectedRun(params.runId); navPush({ page, ...params }); }
  const { dashboard, accumulated, loading, error, availableRuns } = useDashboard({ selectedProject, selectedRun });
  const { overviewRunIndex, currentOverviewRun, handleRunPrev, handleRunNext, handleRunLatest, handleRunView, handleRunSelect } = useRunNavigator({ selectedRun, availableRuns, onRunChange: handleRunChange, onNavigate: handleNavigate });
  const { headerMeta, selectedDisplayName, selectedProjectParent, selectedProjectParentId } = useMemo(() => {
    const meta = computeHeaderMeta(accumulated, dashboard);
    const display = computeProjectDisplay(selectedProject, projects);
    return { headerMeta: meta, ...display };
  }, [accumulated, dashboard, selectedProject, projects]);
  const evalLifecycle = useEvaluationLifecycle({ settings, navigation: { navTab, navReset }, projects: { loadProjects, setProjects, selectProjectAndRun } });
  const activeTab = ['overview', 'history', 'projects', 'evaluate', 'settings'].includes(activePage.page) ? activePage.page : activePage.page === 'history-run' ? 'history' : 'overview';
  const showProjectHeader = ['overview'].includes(activeTab) && projects.length > 0 && !!selectedProject;
  const showRunNav = showProjectHeader && availableRuns.length > 0 && navStack.length === 1;

  return {
    serverConnected, setServerConnected, navStack, activePage, navPop, navGoTo, navTab,
    projects, selectedProject, selectedRun, handleProjectChange, handleNavigate,
    handleDeleteProject, handleExportProject, handleRelocateProject,
    dashboard, accumulated, loading, error, availableRuns, overviewRunIndex,
    currentOverviewRun, handleRunPrev, handleRunNext, handleRunLatest, handleRunView, handleRunSelect,
    headerMeta, selectedDisplayName, selectedProjectParent, selectedProjectParentId,
    evalLifecycle, settings, activeTab, showProjectHeader, showRunNav,
  };
}

export default function App() {
  const state = useAppState();
  const { activePage, navStack, navPop, navGoTo, navTab, activeTab } = state;

  const contentProps = {
    dashboardData: {
      selectedProject: state.selectedProject, selectedRun: state.selectedRun, projects: state.projects,
      dashboard: state.dashboard, accumulated: state.accumulated, loading: state.loading, error: state.error,
      availableRuns: state.availableRuns, overviewRunIndex: state.overviewRunIndex,
    },
    navigation: {
      selectedProject: state.selectedProject, selectedRun: state.selectedRun, projects: state.projects,
      handleNavigate: state.handleNavigate, handleRunSelect: state.handleRunSelect,
      handleProjectChange: state.handleProjectChange, navTab,
      handleDeleteProject: state.handleDeleteProject, handleExportProject: state.handleExportProject, handleRelocateProject: state.handleRelocateProject,
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
              currentOverviewRun: state.currentOverviewRun, overviewRunIndex: state.overviewRunIndex, availableRuns: state.availableRuns,
              onRunPrev: state.handleRunPrev, onRunNext: state.handleRunNext, onRunLatest: state.handleRunLatest,
              onViewRun: activePage.page === 'overview' ? state.handleRunView : undefined,
            },
          }}
        />
      ) : null}
      breadcrumb={navStack.length > 1 ? <NavBreadcrumb stack={navStack} onBack={navPop} onGoTo={navGoTo} /> : null}
      content={<MainContent activePage={activePage} props={contentProps} />}
    />
  );
}
