import { useState, useEffect, useMemo, useRef } from 'react';
import { listProjects, getAiClients } from './api/index.js';
import { useDashboard } from './features/dashboard/hooks/useDashboard.js';
import DashboardPage from './features/dashboard/components/DashboardPage.jsx';
import RunNavigator from './features/dashboard/components/RunNavigator.jsx';
import { useEvaluation } from './features/evaluation/hooks/useEvaluation.js';
import EvaluationForm from './features/evaluation/components/EvaluationForm.jsx';
import EvaluationStatus from './features/evaluation/components/EvaluationStatus.jsx';
import ReEvaluateCard from './features/evaluation/components/ReEvaluateCard.jsx';
import NavBreadcrumb from './features/explorer/components/NavBreadcrumb.jsx';
import ExplorerPage from './features/explorer/components/ExplorerPage.jsx';
import FileDetailPage from './features/explorer/components/FileDetailPage.jsx';
import PrincipleDetailPage from './features/explorer/components/PrincipleDetailPage.jsx';
import EvalPrincipleDetailPage from './features/explorer/components/EvalPrincipleDetailPage.jsx';
import { formatRunId } from './utils/formatters.js';
import ProjectsPage from './features/dashboard/components/ProjectsPage.jsx';


// ---------------------------------------------------------------------------
// Icons
// ---------------------------------------------------------------------------
const ICON_OVERVIEW = (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <rect x="3" y="3" width="7" height="7" rx="1" />
    <rect x="14" y="3" width="7" height="7" rx="1" />
    <rect x="3" y="14" width="7" height="7" rx="1" />
    <rect x="14" y="14" width="7" height="7" rx="1" />
  </svg>
);

const ICON_EVALUATE = (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="11" cy="11" r="7" />
    <line x1="16.5" y1="16.5" x2="22" y2="22" />
  </svg>
);

const ICON_PROJECTS = (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3"  width="4" height="4" rx="0.5" />
    <rect x="3" y="10" width="4" height="4" rx="0.5" />
    <rect x="3" y="17" width="4" height="4" rx="0.5" />
    <line x1="9" y1="5"  x2="21" y2="5"  />
    <line x1="9" y1="12" x2="21" y2="12" />
    <line x1="9" y1="19" x2="21" y2="19" />
  </svg>
);

const ICON_SETTINGS = (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </svg>
);

export default function App() {
  // -------------------------------------------------------------------------
  // Nav stack
  // -------------------------------------------------------------------------
  const [navStack, setNavStack] = useState([{ page: 'overview' }]);

  // Initialize browser history state on mount
  useEffect(() => {
    window.history.replaceState({ navIndex: 0, entry: { page: 'overview' } }, '');
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Sync browser back/forward buttons with navStack
  useEffect(() => {
    function onPopState(e) {
      const targetIndex = e.state?.navIndex ?? 0;
      setNavStack((prev) => {
        if (targetIndex < prev.length - 1) {
          // Going back
          return prev.slice(0, targetIndex + 1);
        }
        if (targetIndex >= prev.length && e.state?.entry) {
          // Going forward — restore entry from history state
          return [...prev.slice(0, targetIndex), e.state.entry];
        }
        return prev;
      });
    }
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  function navPush(entry) {
    setNavStack((prev) => {
      const next = [...prev, entry];
      window.history.pushState({ navIndex: next.length - 1, entry }, '');
      return next;
    });
  }

  function navPop() {
    window.history.back(); // popstate handler updates navStack
  }

  function navGoTo(index) {
    const steps = navStack.length - 1 - index;
    if (steps > 0) window.history.go(-steps); // popstate handler updates navStack
  }

  function navReset() {
    setNavStack((prev) => {
      const stepsBack = prev.length - 1;
      if (stepsBack > 0) window.history.go(-stepsBack);
      return [{ page: 'overview' }];
    });
  }

  function navTab(page) {
    setNavStack((prev) => {
      const stepsBack = prev.length - 1;
      if (stepsBack > 0) window.history.go(-stepsBack);
      return [{ page }];
    });
  }

  const activePage = navStack[navStack.length - 1];

  // Scroll to top on every navigation
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [activePage]);

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
        const list = data.projects || data || [];
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
    await fetch(`/api/projects/${encodeURIComponent(projectId)}${_apiQs()}`, { method: 'DELETE' });
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
  const [overviewRunIndex, setOverviewRunIndex] = useState(0);

  useEffect(() => {
    if (!availableRuns.length) return;
    if (selectedRun === 'latest') {
      setOverviewRunIndex(0);
    } else {
      const idx = availableRuns.findIndex((r) => r.runId === selectedRun);
      if (idx >= 0) setOverviewRunIndex(idx);
    }
  }, [selectedRun, availableRuns]);

  const currentOverviewRun = availableRuns[overviewRunIndex]?.runId || 'latest';

  function handleRunPrev() {
    const idx = Math.min(overviewRunIndex + 1, availableRuns.length - 1);
    setOverviewRunIndex(idx);
    handleRunChange(availableRuns[idx]?.runId || 'latest');
  }

  function handleRunNext() {
    const idx = Math.max(overviewRunIndex - 1, 0);
    setOverviewRunIndex(idx);
    handleRunChange(availableRuns[idx]?.runId || 'latest');
  }

  function handleRunLatest() {
    setOverviewRunIndex(0);
    handleRunChange(availableRuns[0]?.runId || 'latest');
  }

  function handleRunView() {
    handleNavigate('run', { runId: currentOverviewRun });
  }

  function handleRunSelect(runId) {
    const idx = availableRuns.findIndex((r) => r.runId === runId);
    if (idx >= 0) setOverviewRunIndex(idx);
    handleRunChange(runId);
  }

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
    const parentName = data?.parent || null;
    const parentData = parentName ? projects.find((p) => (p.name || p) === parentName) : null;
    const parentId = parentData ? (parentData.id || parentData.name || parentName) : null;
    return {
      selectedDisplayName: data?.displayName || data?.name || selectedProject,
      selectedProjectParent: parentData?.displayName || parentData?.name || parentName,
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
  const [availableClients, setAvailableClients] = useState(null);

  useEffect(() => {
    if (activePage.page !== 'settings' || availableClients !== null) return;
    getAiClients()
      .then((data) => {
        const clients = data.clients || [];
        setAvailableClients(clients);
        if (aiCmd && !clients.some((c) => c.id === aiCmd)) {
          setAiCmd('');
          localStorage.removeItem('cc-ai-cmd');
        }
      })
      .catch(() => setAvailableClients([]));
  }, [activePage]); // eslint-disable-line react-hooks/exhaustive-deps

  function applyAiCmd(value) {
    setAiCmd(value);
    localStorage.setItem('cc-ai-cmd', value);
  }

  // -------------------------------------------------------------------------
  // Evaluation
  // -------------------------------------------------------------------------
  const { job, jobError, liveViolations, startEvaluation, clearJob, cancelEvaluation } = useEvaluation();

  // Auto-navigate to evaluate screen when a running job is discovered (e.g. from another tab)
  const prevJobRef = useRef(null);
  useEffect(() => {
    if (job?.status === 'running' && !prevJobRef.current) {
      navTab('evaluate');
    }
    prevJobRef.current = job;
  }, [job]);

  function handleStartEvaluation(payload) {
    startEvaluation({ ...payload, aiCmd: aiCmd || undefined });
  }

  function handleEvalDismiss(action) {
    if (action === 'view') {
      const project = job?.outputProject;
      const runId = job?.outputRunId;
      if (project) {
        listProjects()
          .then((data) => {
            const list = data.projects || data || [];
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

  function handleNavigate(page, params = {}) {
    if (page === 'run' && params.runId) {
      setSelectedRun(params.runId);
    }
    navPush({ page, ...params });
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
          <section className="evaluate-screen">
            <header className="evaluate-header">
              <div className="evaluate-header-content">
                <div className={`evaluate-icon${job?.status === 'running' ? ' running' : ''}`}>
                  {/* Static layer — visible when idle */}
                  <div className="eval-icon-static">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="11" cy="11" r="7" />
                      <line x1="16.5" y1="16.5" x2="22" y2="22" />
                    </svg>
                  </div>
                  {/* Animated layer — visible when running */}
                  <div className="eval-icon-animated">
                    <span className="eval-file-chip" style={{animationDelay: '0s'}} />
                    <span className="eval-file-chip" style={{animationDelay: '0.55s'}} />
                    <span className="eval-file-chip" style={{animationDelay: '1.1s'}} />
                    <svg className="eval-glass-sweep" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="11" cy="11" r="7" />
                      <line x1="16.5" y1="16.5" x2="22" y2="22" />
                    </svg>
                  </div>
                </div>
                <div>
                  <h1>Evaluate Repository</h1>
                  <p className="evaluate-subtitle">Run a comprehensive code quality evaluation on any repository</p>
                </div>
              </div>
            </header>

            <div className="evaluate-content">
              {!job && selectedProject && (
                <ReEvaluateCard
                  project={selectedProject}
                  onStart={handleStartEvaluation}
                  disabled={false}
                />
              )}

              {!job && (
                <div className="panel evaluate-panel">
                  <div className="panel-header">
                    <h3>{selectedProject ? 'Evaluate a new repository' : 'Evaluate a Repository'}</h3>
                  </div>
                  <EvaluationForm onStart={handleStartEvaluation} disabled={false} />
                </div>
              )}

              {jobError && <div className="job-error-banner">{jobError}</div>}
              <EvaluationStatus job={job} liveViolations={liveViolations} onDismiss={handleEvalDismiss} onCancel={cancelEvaluation} />

              {!job && <div className="panel evaluate-help-panel">
                <div className="panel-header">
                  <h3>How It Works</h3>
                </div>
                <div className="help-steps">
                  <div className="help-step">
                    <div className="step-number">1</div>
                    <div className="step-content">
                      <h4>Provide Repository</h4>
                      <p>Enter a GitHub URL, SSH path, or local filesystem path to the repository you want to evaluate.</p>
                    </div>
                  </div>
                  <div className="help-step">
                    <div className="step-number">2</div>
                    <div className="step-content">
                      <h4>Select Dimensions</h4>
                      <p>Choose which quality dimensions to analyze. Each dimension covers different aspects of code quality.</p>
                    </div>
                  </div>
                  <div className="help-step">
                    <div className="step-number">3</div>
                    <div className="step-content">
                      <h4>Review Results</h4>
                      <p>Once complete, view detailed findings, grades, and actionable recommendations in the Overview.</p>
                    </div>
                  </div>
                </div>
              </div>}
            </div>
          </section>
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
          <div className="settings-page">
            <div className="settings-header">
              <div className="settings-header-content">
                <div className="settings-page-icon">
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
                    <circle cx="12" cy="12" r="3" />
                    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
                  </svg>
                </div>
                <div>
                  <h1 className="settings-title">Settings</h1>
                  <p className="settings-subtitle">Manage your Quodeq preferences</p>
                </div>
              </div>
            </div>

            <div className="settings-body">
              <section className="panel settings-section">
                <div className="panel-header">
                  <h2 className="settings-section-title">Appearance</h2>
                </div>
                <div className="settings-row">
                  <div className="settings-row-label">
                    <span className="settings-label">Theme</span>
                    <span className="settings-description">Choose how Quodeq looks to you</span>
                  </div>
                  <div className="theme-toggle">
                    {[
                      { value: 'system',    label: 'System' },
                      { value: 'light',     label: 'Light' },
                      { value: 'dark',      label: 'Dark' },
                      { value: 'media-light', label: 'Media Light' },
                      { value: 'media-dark',  label: 'Media Dark' },
                    ].map(({ value, label }) => (
                      <button
                        key={value}
                        type="button"
                        className={`theme-toggle-btn${themePreference === value ? ' active' : ''}`}
                        onClick={() => applyTheme(value)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
              </section>

              <section className="panel settings-section">
                <div className="panel-header">
                  <h2 className="settings-section-title">Analysis</h2>
                  <p className="settings-section-description">Configure the AI client used when running evaluations</p>
                </div>
                <div className={`settings-row${!aiCmd ? ' settings-row--last' : ''}`}>
                  <div className="settings-row-label">
                    <span className="settings-label">Client</span>
                    <span className="settings-description">CLI tool used to run the analysis</span>
                  </div>
                  {availableClients === null ? (
                    <span className="settings-description">Detecting…</span>
                  ) : availableClients.length > 0 ? (
                    <div className="theme-toggle">
                      {availableClients.map(({ id, label }) => (
                        <button
                          key={id}
                          type="button"
                          className={`theme-toggle-btn${aiCmd === id ? ' active' : ''}`}
                          onClick={() => applyAiCmd(id)}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
                {availableClients !== null && availableClients.length === 0 && (
                  <div className="settings-row settings-row--last settings-install-guide">
                    <div className="settings-row-label">
                      <span className="settings-label">No AI client detected</span>
                      <span className="settings-description">
                        Install one of the supported CLI tools and restart Quodeq.
                      </span>
                    </div>
                    <div className="settings-install-options">
                      <div className="settings-install-item">
                        <span className="settings-install-name">Claude</span>
                        <code className="settings-install-cmd">npm i -g @anthropic-ai/claude-code</code>
                      </div>
                      <div className="settings-install-item">
                        <span className="settings-install-name">Codex</span>
                        <code className="settings-install-cmd">npm i -g @openai/codex</code>
                      </div>
                      <div className="settings-install-item">
                        <span className="settings-install-name">Copilot</span>
                        <code className="settings-install-cmd">gh extension install github/gh-copilot</code>
                      </div>
                    </div>
                  </div>
                )}
                {aiCmd && (
                  <div className="settings-row settings-row--last">
                    <div className="settings-row-label">
                      <span className="settings-label">Model</span>
                      <span className="settings-description">
                        Uses your client's default model. Run <code>{aiCmd} --help</code> to see how to change it.
                      </span>
                    </div>
                  </div>
                )}
              </section>
            </div>
          </div>
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
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="sidebar-brand-icon">
            <img src="/logo.png" alt="Quodeq" width="36" height="36" />
          </div>
          <span className="sidebar-brand-text">Quodeq</span>
        </div>

        <nav className="sidebar-nav">
          <button
            type="button"
            className={`sidebar-nav-item${activeTab === 'overview' ? ' active' : ''}`}
            onClick={() => navTab('overview')}
            title="Overview"
          >
            {ICON_OVERVIEW}
            <span className="sidebar-nav-label">Overview</span>
          </button>

          <button
            type="button"
            className={`sidebar-nav-item${activeTab === 'evaluate' ? ' active' : ''}`}
            onClick={() => navTab('evaluate')}
            title="Evaluate"
          >
            {ICON_EVALUATE}
            <span className="sidebar-nav-label">Evaluate</span>
          </button>

          <button
            type="button"
            className={`sidebar-nav-item${activeTab === 'projects' ? ' active' : ''}`}
            onClick={() => navTab('projects')}
            title="Projects"
          >
            {ICON_PROJECTS}
            <span className="sidebar-nav-label">Projects</span>
          </button>
        </nav>

        {/* Settings at bottom */}
        <div className="sidebar-bottom-nav">
          <button
            type="button"
            className={`sidebar-nav-item${activeTab === 'settings' ? ' active' : ''}`}
            onClick={() => navTab('settings')}
            title="Settings"
          >
            {ICON_SETTINGS}
            <span className="sidebar-nav-label">Settings</span>
          </button>
        </div>

      </aside>

      {/* Main content */}
      <main className="dashboard">
        {/* Persistent project header — shown on all data pages */}
        {showProjectHeader && (
          <header className="content-header">
            <div className="content-header-left">
              <h1 className="content-project-name">
                {selectedProjectParent && (
                  <>
                    <span
                      className="content-project-parent content-project-parent--link"
                      role="button"
                      tabIndex={0}
                      onClick={() => selectedProjectParentId && handleProjectChange(selectedProjectParentId)}
                      onKeyDown={(e) => { if (e.key === 'Enter' && selectedProjectParentId) handleProjectChange(selectedProjectParentId); }}
                    >{selectedProjectParent}</span>
                    <span className="content-project-sep">›</span>
                  </>
                )}
                {selectedDisplayName}
              </h1>
              {headerMeta && (
                <div className="content-meta-row">
                  {headerMeta.repository && (
                    <span className="content-meta-chip">
                      <span className="content-meta-chip-label">Repository</span>
                      <span className="content-meta-chip-value">{headerMeta.repository}</span>
                    </span>
                  )}
                  {headerMeta.discipline && (
                    <span className="content-meta-chip">
                      <span className="content-meta-chip-label">Discipline</span>
                      <span className="content-meta-chip-value">{headerMeta.discipline}</span>
                    </span>
                  )}
                  {headerMeta.totalFiles && (
                    <span className="content-meta-chip">
                      <span className="content-meta-chip-label">Source files</span>
                      <span className="content-meta-chip-value">{headerMeta.totalFiles.toLocaleString()}</span>
                    </span>
                  )}
                </div>
              )}
            </div>
            {showRunNav && (
              <RunNavigator
                currentRun={formatRunId(currentOverviewRun, availableRuns[overviewRunIndex]?.dateLabel)}
                isLatest={overviewRunIndex === 0}
                isOldest={overviewRunIndex >= availableRuns.length - 1}
                onPrev={handleRunPrev}
                onNext={handleRunNext}
                onLatest={handleRunLatest}
                onView={onViewRun}
              />
            )}
          </header>
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
