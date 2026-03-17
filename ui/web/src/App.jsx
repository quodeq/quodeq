import { useState, useEffect, useMemo, useRef } from 'react';
import { listProjects } from './api/index.js';
import { useDashboard } from './features/dashboard/hooks/useDashboard.js';
import DashboardPage from './features/dashboard/components/DashboardPage.jsx';
import { useEvaluation } from './features/evaluation/hooks/useEvaluation.js';
import { getLevels, MODEL_STORAGE_PREFIX, STORAGE_KEY as POWER_KEY } from './features/evaluation/components/powerLevels.js';
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


export default function App() {
  // -------------------------------------------------------------------------
  // Server connection monitor
  // -------------------------------------------------------------------------
  const [serverConnected, setServerConnected] = useServerHealth();

  // -------------------------------------------------------------------------
  // Nav stack
  // -------------------------------------------------------------------------
  const { navStack, activePage, navPush, navPop, navGoTo, navReset, navTab } = useNavStack();

  // -------------------------------------------------------------------------
  // Project / run selection
  // -------------------------------------------------------------------------
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(() => {
    try { return localStorage.getItem('quodeq_selected_project') || ''; } catch { return ''; }
  });
  const [selectedRun, setSelectedRun] = useState('latest');

  function loadProjects() {
    listProjects()
      .then((data) => {
        const list = Array.isArray(data) ? data : (data?.projects || []);
        setProjects(list);
        if (list.length > 0) {
          const current = selectedProject || localStorage.getItem('quodeq_selected_project') || '';
          const match = current && list.find((p) => (p.id || p.name) === current);
          if (!match) {
            const pick = list[0].id || list[0].name || list[0];
            handleProjectChange(pick);
          }
        } else if (list.length === 0) {
          navTab('evaluate');
        }
      })
      .catch(() => {});
  }

  useEffect(() => {
    loadProjects();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function handleProjectChange(name) {
    setSelectedProject(name);
    try { localStorage.setItem('quodeq_selected_project', name); } catch {}
    setSelectedRun('latest');
    navReset();
  }

  function _apiQs() {
    const params = new URLSearchParams(window.location.search);
    const dir = params.get('evaluations') || '';
    return dir ? `?evaluations=${encodeURIComponent(dir)}` : '';
  }

  async function handleDeleteProject(projectId) {
    const qs = _apiQs();
    const separator = qs ? '&' : '?';
    const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}${qs}${separator}confirm=true`, { method: 'DELETE' });
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
    await fetch(`/api/projects/${encodeURIComponent(projectId)}/path${_apiQs()}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: newPath }),
    });
    loadProjects();
  }

  function handleRunChange(runId) { setSelectedRun(runId); }

  function handleNavigate(page, params = {}) {
    if (page === 'run' && params.runId) {
      setSelectedRun(params.runId);
    }
    navPush({ page, ...params });
  }

  // -------------------------------------------------------------------------
  // Dashboard data (shared across all pages)
  // -------------------------------------------------------------------------
  const { dashboard, accumulated, loading, error, availableRuns } = useDashboard({
    selectedProject,
    selectedRun,
  });

  // -------------------------------------------------------------------------
  // Run navigator state (lifted from DashboardPage)
  // -------------------------------------------------------------------------
  const {
    overviewRunIndex,
    currentOverviewRun,
    handleRunPrev,
    handleRunNext,
    handleRunLatest,
    handleRunView,
    handleRunSelect,
  } = useRunNavigator({
    selectedRun,
    availableRuns,
    onRunChange: handleRunChange,
    onNavigate: handleNavigate,
  });

  // -------------------------------------------------------------------------
  // Header meta (discipline, repository, source files)
  // -------------------------------------------------------------------------
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

  // -------------------------------------------------------------------------
  // Theme
  // -------------------------------------------------------------------------
  const [themePreference, setThemePreference] = useState(
    localStorage.getItem('cc-theme') || 'system'
  );

  function applyTheme(value) {
    setThemePreference(value);
    if (value === 'system') {
      localStorage.removeItem('cc-theme');
      document.documentElement.removeAttribute('data-theme');
    } else {
      localStorage.setItem('cc-theme', value);
      document.documentElement.setAttribute('data-theme', value);
    }
  }

  // -------------------------------------------------------------------------
  // AI settings
  // -------------------------------------------------------------------------
  const [aiCmd, setAiCmd] = useState(localStorage.getItem('cc-ai-cmd') || '');
  const [aiModel, setAiModel] = useState(localStorage.getItem('cc-ai-model') || '');
  const [modelFast, setModelFast] = useState(localStorage.getItem(`${MODEL_STORAGE_PREFIX}1`) || '');
  const [modelBalanced, setModelBalanced] = useState(localStorage.getItem(`${MODEL_STORAGE_PREFIX}2`) || '');
  const [modelThorough, setModelThorough] = useState(localStorage.getItem(`${MODEL_STORAGE_PREFIX}3`) || '');
  const [verifyFindings, setVerifyFindings] = useState(() => {
    try { return localStorage.getItem('cc-verify-findings') !== 'false'; } catch { return true; }
  });

  function applyAiCmd(value) {
    setAiCmd(value);
    if (value) {
      localStorage.setItem('cc-ai-cmd', value);
    } else {
      localStorage.removeItem('cc-ai-cmd');
    }
  }

  function applyVerifyFindings(value) {
    setVerifyFindings(value);
    localStorage.setItem('cc-verify-findings', value ? 'true' : 'false');
  }

  // -------------------------------------------------------------------------
  // Evaluation
  // -------------------------------------------------------------------------
  const { job, jobError, liveViolations, startEvaluation, clearJob, cancelEvaluation } = useEvaluation();
  const [analysisPower, setAnalysisPower] = useState(() => {
    try { return Number(localStorage.getItem(POWER_KEY)) || 2; } catch { return 2; }
  });

  // Auto-navigate to evaluate screen when a running job is discovered (e.g. from another tab)
  const prevJobRef = useRef(null);
  useEffect(() => {
    if (job?.status === 'running' && !prevJobRef.current) {
      navTab('evaluate');
    }
    prevJobRef.current = job;
  }, [job]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleStartEvaluation(payload) {
    const levels = getLevels();
    const subagentModel = levels.find(l => l.level === analysisPower)?.model;
    startEvaluation({ ...payload, aiCmd: aiCmd || undefined, aiModel: aiModel || undefined, subagentModel, verifyFindings });
  }

  function handleEvalDismiss(action) {
    if (action === 'view') {
      const project = job?.outputProject;
      const runId = job?.outputRunId;
      if (project) {
        listProjects()
          .then((data) => {
            const list = Array.isArray(data) ? data : (data?.projects || []);
            setProjects(list);
            setSelectedProject(project);
            setSelectedRun(runId || 'latest');
          })
          .catch(() => {
            setSelectedProject(project);
            setSelectedRun(runId || 'latest');
          });
      }
      navReset();
    }
    clearJob();
  }

  // -------------------------------------------------------------------------
  // Active tab / header visibility
  // -------------------------------------------------------------------------
  const activeTab = ['overview', 'projects', 'evaluate', 'settings'].includes(activePage.page)
    ? activePage.page
    : 'overview';

  // Show the project header on all data pages; hide it on evaluate and settings.
  const showProjectHeader = ['overview'].includes(activeTab) && projects.length > 0 && !!selectedProject;

  // Show the run navigator only on top-level data pages (not when drilled into a sub-page).
  const showRunNav = showProjectHeader && availableRuns.length > 0 && navStack.length === 1;

  // "View run" button only on the top-level overview (not when already in run mode or inner pages).
  const onViewRun = activePage.page === 'overview' ? handleRunView : undefined;

  // -------------------------------------------------------------------------
  // Content renderer
  // -------------------------------------------------------------------------
  function renderContent() {
    const { page, ...params } = activePage;

    switch (page) {
      case 'overview':
        return (
          <DashboardPage
            selectedProject={selectedProject}
            selectedRun={selectedRun}
            projects={projects}
            onNavigate={handleNavigate}
            onRunSelect={handleRunSelect}
            dashboard={dashboard}
            accumulated={accumulated}
            loading={loading}
            error={error}
            availableRuns={availableRuns}
            overviewRunIndex={overviewRunIndex}
          />
        );

      case 'run':
        return (
          <DashboardPage
            selectedProject={selectedProject}
            selectedRun={selectedRun}
            projects={projects}
            onNavigate={handleNavigate}
            dashboard={dashboard}
            accumulated={accumulated}
            loading={loading}
            error={error}
            availableRuns={availableRuns}
            overviewRunIndex={overviewRunIndex}
            runMode={true}
          />
        );

      case 'explorer':
        return (
          <ExplorerPage
            project={selectedProject}
            dimension={params.dimension}
            runId={params.runId}
            dateLabel={params.dateLabel}
            onNavigate={handleNavigate}
          />
        );

      case 'evaluate':
        return (
          <EvaluateScreen
            job={job}
            jobError={jobError}
            liveViolations={liveViolations}
            selectedProject={selectedProject}
            analysisPower={analysisPower}
            onAnalysisPowerChange={setAnalysisPower}
            onStartEvaluation={handleStartEvaluation}
            onDismiss={handleEvalDismiss}
            onCancel={cancelEvaluation}
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
            themePreference={themePreference}
            onApplyTheme={applyTheme}
            aiCmd={aiCmd}
            onApplyAiCmd={applyAiCmd}
            aiModel={aiModel}
            onAiModelChange={setAiModel}
            modelFast={modelFast}
            onModelFastChange={setModelFast}
            modelBalanced={modelBalanced}
            onModelBalancedChange={setModelBalanced}
            modelThorough={modelThorough}
            onModelThoroughChange={setModelThorough}
            analysisPower={analysisPower}
            onAnalysisPowerChange={setAnalysisPower}
            verifyFindings={verifyFindings}
            onApplyVerifyFindings={applyVerifyFindings}
          />
        );

      case 'projects':
        return (
          <ProjectsPage
            projects={projects}
            selectedProject={selectedProject}
            onSelect={handleProjectChange}
            onDelete={handleDeleteProject}
            onExport={handleExportProject}
            onRelocate={handleRelocateProject}
          />
        );

      default:
        return <div className="empty-state"><p>Page not found: {page}</p></div>;
    }
  }

  // -------------------------------------------------------------------------
  // Layout
  // -------------------------------------------------------------------------
  return (
    <div className="app-shell">
      {!serverConnected && (
        <ServerDisconnectedOverlay onReconnect={() => setServerConnected(true)} />
      )}

      <Sidebar activeTab={activeTab} onNavTab={navTab} />

      {/* Main content */}
      <main className="dashboard">
        {/* Persistent project header — shown on all data pages */}
        {showProjectHeader && (
          <ProjectHeader
            selectedDisplayName={selectedDisplayName}
            selectedProjectParent={selectedProjectParent}
            selectedProjectParentId={selectedProjectParentId}
            onProjectChange={handleProjectChange}
            headerMeta={headerMeta}
            showRunNav={showRunNav}
            currentOverviewRun={currentOverviewRun}
            overviewRunIndex={overviewRunIndex}
            availableRuns={availableRuns}
            onRunPrev={handleRunPrev}
            onRunNext={handleRunNext}
            onRunLatest={handleRunLatest}
            onViewRun={onViewRun}
          />
        )}

        {/* Breadcrumb — shown when navigating into sub-pages */}
        {navStack.length > 1 && (
          <NavBreadcrumb stack={navStack} onBack={navPop} onGoTo={navGoTo} />
        )}

        {renderContent()}
      </main>
    </div>
  );
}
