import { useState, useEffect, useMemo, useRef } from 'react';
import { useDashboard } from './features/dashboard/hooks/useDashboard.js';
import DashboardPage from './features/dashboard/components/DashboardPage.jsx';
import { useEvaluation } from './features/evaluation/hooks/useEvaluation.js';
import { getLevels, STORAGE_KEY as POWER_KEY } from './features/evaluation/components/powerLevels.js';
import NavBreadcrumb from './features/explorer/components/NavBreadcrumb.jsx';
import ExplorerPage from './features/explorer/components/ExplorerPage.jsx';
import FileDetailPage from './features/explorer/components/FileDetailPage.jsx';
import PrincipleDetailPage from './features/explorer/components/PrincipleDetailPage.jsx';
import EvalPrincipleDetailPage from './features/explorer/components/EvalPrincipleDetailPage.jsx';
import ProjectsPage from './features/dashboard/components/ProjectsPage.jsx';
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


export default function App() {
  const [serverConnected, setServerConnected] = useServerHealth();
  const { navStack, activePage, navPush, navPop, navGoTo, navReset, navTab } = useNavStack();

  // Project / run selection
  const {
    projects, setProjects, selectedProject, selectedRun, setSelectedRun,
    loadProjects, handleProjectChange, handleRunChange, selectProjectAndRun,
  } = useProjectState({ onNoProjects: () => navTab('evaluate') });

  // Theme + AI settings
  const settings = useAppSettings();

  function _apiQs() {
    const params = new URLSearchParams(window.location.search);
    const dir = params.get('evaluations') || '';
    return dir ? `?evaluations=${encodeURIComponent(dir)}` : '';
  }

  async function handleDeleteProject(projectId) {
    const qs = _apiQs();
    const separator = qs ? '&' : '?';
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);
    const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}${qs}${separator}confirm=true`, { method: 'DELETE', signal: controller.signal });
    clearTimeout(timeoutId);
    if (!res.ok) {
      const msg = await res.text().catch(() => res.statusText);
      alert(`Failed to delete project: ${msg}`);
      return;
    }
    if (selectedProject === projectId) handleProjectChange(projects.find((p) => (p.id || p.name || p) !== projectId)?.id ?? '');
    loadProjects();
  }

  function handleExportProject(projectId) {
    const qs = _apiQs();
    const url = `/api/projects/${encodeURIComponent(projectId)}/export${qs}`;
    const proj = projects.find((p) => (p.id || p.name) === projectId);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${proj?.name || projectId}.zip`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  async function handleRelocateProject(projectId, newPath) {
    try {
      const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}/path${_apiQs()}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: newPath }),
      });
      if (!res.ok) {
        console.error('Relocate failed:', res.status);
        alert('Failed to relocate project. Please try again.');
        return;
      }
    } catch (err) {
      console.error('Relocate failed:', err);
      alert('Failed to relocate project. Please try again.');
      return;
    }
    loadProjects();
  }

  function handleNavigate(page, params = {}) {
    if (page === 'run' && params.runId) setSelectedRun(params.runId);
    navPush({ page, ...params });
  }

  // Dashboard data
  const { dashboard, accumulated, loading, error, availableRuns } = useDashboard({
    selectedProject,
    selectedRun,
  });

  // Run navigator
  const {
    overviewRunIndex, currentOverviewRun,
    handleRunPrev, handleRunNext, handleRunLatest, handleRunView, handleRunSelect,
  } = useRunNavigator({
    selectedRun, availableRuns,
    onRunChange: handleRunChange,
    onNavigate: handleNavigate,
  });

  // Header meta
  const headerMeta = useMemo(() => {
    const accDims = accumulated?.dimensions || [];
    if (accDims.length === 0) return null;
    const discipline = accDims.find((d) => d.discipline)?.discipline ?? null;
    const repository = accDims.find((d) => d.repository)?.repository ?? null;
    const runDims = dashboard?.dimensions || [];
    const totalFiles = runDims.find((d) => d.sourceFileCount)?.sourceFileCount ?? null;
    return { discipline, repository, totalFiles };
  }, [accumulated, dashboard]);

  const { selectedDisplayName, selectedProjectParent, selectedProjectParentId } = useMemo(() => {
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
  }, [selectedProject, projects]);

  // Evaluation
  const { job, jobError, liveViolations, startEvaluation, clearJob, cancelEvaluation } = useEvaluation();
  const [analysisPower, setAnalysisPower] = useState(() => {
    try { return Number(localStorage.getItem(POWER_KEY)) || 2; } catch (e) { console.warn('localStorage unavailable:', e); return 2; }
  });

  const prevJobRef = useRef(null);
  useEffect(() => {
    if (job?.status === 'running' && !prevJobRef.current) navTab('evaluate');
    prevJobRef.current = job;
  }, [job]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleStartEvaluation(payload) {
    const levels = getLevels();
    const subagentModel = levels.find(l => l.level === analysisPower)?.model;
    startEvaluation({ ...payload, aiCmd: settings.aiCmd || undefined, aiModel: settings.aiModel || undefined, subagentModel, verifyFindings: settings.verifyFindings });
  }

  function handleEvalDismiss(action) {
    if (action === 'view') {
      const project = job?.outputProject;
      const runId = job?.outputRunId;
      if (project) {
        loadProjects()
          .then((list) => setProjects(list))
          .catch((err) => console.error('Operation failed:', err));
        selectProjectAndRun(project, runId);
      }
      navReset();
    }
    clearJob();
  }

  // Active tab / header visibility
  const activeTab = ['overview', 'projects', 'evaluate', 'settings'].includes(activePage.page)
    ? activePage.page : 'overview';
  const showProjectHeader = ['overview'].includes(activeTab) && projects.length > 0 && !!selectedProject;
  const showRunNav = showProjectHeader && availableRuns.length > 0 && navStack.length === 1;
  const onViewRun = activePage.page === 'overview' ? handleRunView : undefined;

  // Content renderer
  function renderContent() {
    const { page, ...params } = activePage;
    switch (page) {
      case 'overview':
      case 'run':
        return (
          <DashboardPage
            selectedProject={selectedProject} selectedRun={selectedRun} projects={projects}
            onNavigate={handleNavigate} onRunSelect={page === 'overview' ? handleRunSelect : undefined}
            dashboard={dashboard} accumulated={accumulated} loading={loading} error={error}
            availableRuns={availableRuns} overviewRunIndex={overviewRunIndex}
            runMode={page === 'run'}
          />
        );
      case 'explorer':
        return <ExplorerPage project={selectedProject} dimension={params.dimension} runId={params.runId} dateLabel={params.dateLabel} onNavigate={handleNavigate} />;
      case 'evaluate':
        return (
          <EvaluateScreen
            evaluation={{ job, jobError, liveViolations }}
            context={{ selectedProject, analysisPower, onAnalysisPowerChange: setAnalysisPower }}
            actions={{ onStart: handleStartEvaluation, onDismiss: handleEvalDismiss, onCancel: cancelEvaluation }}
          />
        );
      case 'file':
        return <FileDetailPage file={params.file} />;
      case 'principle':
        return <PrincipleDetailPage principle={params.principle} />;
      case 'evalprinciple':
      case 'eval-principle-detail':
        return <EvalPrincipleDetailPage evalPrincipal={params.evalPrincipal} />;
      case 'settings':
        return (
          <SettingsPage
            theme={{ preference: settings.themePreference, onApply: settings.applyTheme }}
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
      case 'projects':
        return <ProjectsPage projects={projects} selectedProject={selectedProject} onSelect={handleProjectChange} onDelete={handleDeleteProject} onExport={handleExportProject} onRelocate={handleRelocateProject} />;
      default:
        return <div className="empty-state"><p>Page not found: {page}</p></div>;
    }
  }

  return (
    <div className="app-shell">
      {!serverConnected && <ServerDisconnectedOverlay onReconnect={() => setServerConnected(true)} />}
      <Sidebar activeTab={activeTab} onNavTab={navTab} />
      <main className="dashboard">
        {showProjectHeader && (
          <ProjectHeader
            selectedDisplayName={selectedDisplayName} selectedProjectParent={selectedProjectParent}
            selectedProjectParentId={selectedProjectParentId} onProjectChange={handleProjectChange}
            headerMeta={headerMeta} showRunNav={showRunNav}
            runNavProps={{
              currentOverviewRun, overviewRunIndex, availableRuns,
              onRunPrev: handleRunPrev, onRunNext: handleRunNext,
              onRunLatest: handleRunLatest, onViewRun: onViewRun,
            }}
          />
        )}
        {navStack.length > 1 && <NavBreadcrumb stack={navStack} onBack={navPop} onGoTo={navGoTo} />}
        {renderContent()}
      </main>
    </div>
  );
}
