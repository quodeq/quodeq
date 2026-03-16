import { useState, useEffect, useMemo, useRef } from 'react';
import { listProjects, getAiClients, getHealth } from './api/index.js';
import { useDashboard } from './features/dashboard/hooks/useDashboard.js';
import DashboardPage from './features/dashboard/components/DashboardPage.jsx';
import RunNavigator from './features/dashboard/components/RunNavigator.jsx';
import { useEvaluation } from './features/evaluation/hooks/useEvaluation.js';
import EvaluationForm from './features/evaluation/components/EvaluationForm.jsx';
import EvaluationStatus from './features/evaluation/components/EvaluationStatus.jsx';
import ReEvaluateCard from './features/evaluation/components/ReEvaluateCard.jsx';
import PowerSelector from './features/evaluation/components/PowerSelector.jsx';
import { getLevels, DEFAULT_MODELS, MODEL_STORAGE_PREFIX, STORAGE_KEY as POWER_KEY } from './features/evaluation/components/powerLevels.js';
import NavBreadcrumb from './features/explorer/components/NavBreadcrumb.jsx';
import ExplorerPage from './features/explorer/components/ExplorerPage.jsx';
import FileDetailPage from './features/explorer/components/FileDetailPage.jsx';
import PrincipleDetailPage from './features/explorer/components/PrincipleDetailPage.jsx';
import EvalPrincipleDetailPage from './features/explorer/components/EvalPrincipleDetailPage.jsx';
import { formatRunId } from './utils/formatters.js';
import ProjectsPage from './features/dashboard/components/ProjectsPage.jsx';
import SettingsAside from './features/settings/components/SettingsAside.jsx';


// ---------------------------------------------------------------------------
// Icons
// ---------------------------------------------------------------------------
const ICON_OVERVIEW = (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="13" width="4" height="8" />
    <rect x="10" y="8" width="4" height="13" />
    <rect x="17" y="3" width="4" height="18" />
  </svg>
);

const ICON_EVALUATE = (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="11" cy="11" r="7" />
    <line x1="16.5" y1="16.5" x2="21" y2="21" />
    <line x1="8" y1="11" x2="14" y2="11" />
    <line x1="11" y1="8" x2="11" y2="14" />
  </svg>
);

const ICON_PROJECTS = (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="3,4 5.5,6 3,8" />
    <line x1="9" y1="6" x2="21" y2="6" />
    <polyline points="3,11 5.5,13 3,15" />
    <line x1="9" y1="13" x2="21" y2="13" />
    <polyline points="3,18 5.5,20 3,22" />
    <line x1="9" y1="20" x2="21" y2="20" />
  </svg>
);

const ICON_SETTINGS = (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3" />
    <path d="M12 2v2.5M12 19.5V22M4.93 4.93l1.77 1.77M17.3 17.3l1.77 1.77M2 12h2.5M19.5 12H22M4.93 19.07l1.77-1.77M17.3 6.7l1.77-1.77" />
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
  const [modelFast, setModelFast] = useState(localStorage.getItem(`${MODEL_STORAGE_PREFIX}1`) || '');
  const [modelBalanced, setModelBalanced] = useState(localStorage.getItem(`${MODEL_STORAGE_PREFIX}2`) || '');
  const [modelThorough, setModelThorough] = useState(localStorage.getItem(`${MODEL_STORAGE_PREFIX}3`) || '');
  const [verifyFindings, setVerifyFindings] = useState(() => {
    try { return localStorage.getItem('cc-verify-findings') !== 'false'; } catch { return true; }
  });
  const [availableClients, setAvailableClients] = useState(null);
  const [appVersion, setAppVersion] = useState(null);
  const [settingsPhrase, setSettingsPhrase] = useState('');

  const _SETTINGS_PHRASES = [
    'quode with cuore ♥',
    'human aligned quode',
    'quode safe',
    'navigate your quode to excellence',
    'code quality compass',
  ];

  useEffect(() => {
    if (activePage.page !== 'settings') return;
    setSettingsPhrase(_SETTINGS_PHRASES[Math.floor(Math.random() * _SETTINGS_PHRASES.length)]);
    if (appVersion === null) {
      getHealth().then((d) => setAppVersion(d.version || null)).catch(() => {});
    }
  }, [activePage]); // eslint-disable-line react-hooks/exhaustive-deps

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
        if (!aiCmd && clients.length > 0) {
          applyAiCmd(clients[0].id);
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
  }, [job]);

  function applyVerifyFindings(value) {
    setVerifyFindings(value);
    localStorage.setItem('cc-verify-findings', value ? 'true' : 'false');
  }

  function handleStartEvaluation(payload) {
    const levels = getLevels();
    const subagentModel = levels.find(l => l.level === analysisPower)?.model;
    startEvaluation({ ...payload, aiCmd: aiCmd || undefined, subagentModel, verifyFindings });
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
                      <line x1="16.5" y1="16.5" x2="21" y2="21" />
                      <line x1="8" y1="11" x2="14" y2="11" />
                      <line x1="11" y1="8" x2="11" y2="14" />
                    </svg>
                  </div>
                  {/* Animated layer — visible when running */}
                  <div className="eval-icon-animated">
                    <span className="eval-file-chip" style={{animationDelay: '0s'}} />
                    <span className="eval-file-chip" style={{animationDelay: '0.55s'}} />
                    <span className="eval-file-chip" style={{animationDelay: '1.1s'}} />
                    <svg className="eval-glass-sweep" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="11" cy="11" r="7" />
                      <line x1="16.5" y1="16.5" x2="21" y2="21" />
                      <line x1="8" y1="11" x2="14" y2="11" />
                      <line x1="11" y1="8" x2="11" y2="14" />
                    </svg>
                  </div>
                </div>
                <div>
                  <h1>Evaluate Repository</h1>
                  <p className="evaluate-subtitle">Run a comprehensive code quality evaluation on any repository</p>
                </div>
              </div>
              <PowerSelector value={analysisPower} onChange={setAnalysisPower} />
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
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="3" />
                    <path d="M12 2v2.5M12 19.5V22M4.93 4.93l1.77 1.77M17.3 17.3l1.77 1.77M2 12h2.5M19.5 12H22M4.93 19.07l1.77-1.77M17.3 6.7l1.77-1.77" />
                  </svg>
                </div>
                <div>
                  <h1 className="settings-title">Settings</h1>
                  <p className="settings-subtitle">Manage your Quodeq preferences</p>
                </div>
              </div>
            </div>

            <div className="settings-layout">
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
                      { value: 'system',      label: 'System' },
                      { value: 'light',       label: 'Light' },
                      { value: 'dark',        label: 'Dark' },
                      { value: 'ember',       label: 'Ember' },
                      { value: 'forest',      label: 'Forest' },
                      { value: 'midnight',    label: 'Midnight' },
                      { value: 'slate',       label: 'Slate' },
                      { value: 'horizon',     label: 'Horizon' },
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
                  ) : availableClients.filter((c) => c.id === 'claude').length > 0 ? (
                    <div className="theme-toggle">
                      {availableClients.filter((c) => c.id === 'claude').map(({ id, label }) => (
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
                {availableClients !== null && !availableClients.some((c) => c.id === 'claude') && (
                  <div className="settings-row settings-row--last settings-install-guide">
                    <div className="settings-row-label">
                      <span className="settings-label">Claude not detected</span>
                      <span className="settings-description">
                        Install Claude Code and restart Quodeq.
                      </span>
                    </div>
                    <div className="settings-install-options">
                      <div className="settings-install-item">
                        <span className="settings-install-name">Claude</span>
                        <code className="settings-install-cmd">npm i -g @anthropic-ai/claude-code</code>
                      </div>
                    </div>
                  </div>
                )}
                {aiCmd && (
                  <div className="settings-row">
                    <div className="settings-row-label">
                      <span className="settings-label">Model</span>
                      <span className="settings-description">
                        Uses your client's default model. Run <code>{aiCmd} --help</code> to see how to change it.
                      </span>
                    </div>
                  </div>
                )}
                <div className="settings-row">
                  <div className="settings-row-label">
                    <span className="settings-label">Analysis power</span>
                    <span className="settings-description">
                      Controls the AI model used for analysis. Higher power gives more thorough results but takes longer.
                    </span>
                  </div>
                  <PowerSelector value={analysisPower} onChange={setAnalysisPower} />
                </div>
                {aiCmd && (
                  <div className="settings-row">
                    <div className="settings-row-label">
                      <span className="settings-label">Analysis models</span>
                      <span className="settings-description">
                        Override the AI model used by subagents during code evaluation. Leave blank to use the defaults.
                      </span>
                    </div>
                    <div className="settings-model-overrides">
                    {[
                      { label: 'Fast', value: modelFast, setter: setModelFast, level: 1, placeholder: DEFAULT_MODELS[1] },
                      { label: 'Balanced', value: modelBalanced, setter: setModelBalanced, level: 2, placeholder: DEFAULT_MODELS[2] },
                      { label: 'Thorough', value: modelThorough, setter: setModelThorough, level: 3, placeholder: DEFAULT_MODELS[3] },
                    ].map(({ label, value, setter, level, placeholder }) => (
                      <div key={level} className="settings-model-field">
                        <label className="settings-model-label">{label}</label>
                        <input
                          type="text"
                          className="settings-model-input"
                          value={value}
                          placeholder={placeholder}
                          onChange={(e) => {
                            const v = e.target.value;
                            setter(v);
                            if (v) {
                              localStorage.setItem(`${MODEL_STORAGE_PREFIX}${level}`, v);
                            } else {
                              localStorage.removeItem(`${MODEL_STORAGE_PREFIX}${level}`);
                            }
                          }}
                        />
                      </div>
                    ))}
                    </div>
                  </div>
                )}
                <div className="settings-row settings-row--last">
                  <div className="settings-row-label">
                    <span className="settings-label">Verify findings</span>
                    <span className="settings-description">
                      After analysis, verify findings from the previous evaluation against the current code. Confirms which violations persist, detects fixes, and hunts for missing compliance evidence. Improves grade consistency across runs.
                    </span>
                  </div>
                  <div className="theme-toggle">
                    <button
                      type="button"
                      className={`theme-toggle-btn${verifyFindings ? ' active' : ''}`}
                      onClick={() => applyVerifyFindings(true)}
                    >On</button>
                    <button
                      type="button"
                      className={`theme-toggle-btn${!verifyFindings ? ' active' : ''}`}
                      onClick={() => applyVerifyFindings(false)}
                    >Off</button>
                  </div>
                </div>
              </section>
              <section className="panel settings-section">
                <div className="panel-header">
                  <h2 className="settings-section-title">About</h2>
                </div>
                <div className="settings-about-rows">
                  <div className="settings-about-row">
                    <span className="settings-about-key">Version</span>
                    <span className="settings-about-value">{appVersion ?? '—'}</span>
                  </div>
                  <div className="settings-about-row">
                    <span className="settings-about-key">Website</span>
                    <a className="settings-about-link" href="https://quodeq.ai" target="_blank" rel="noopener noreferrer">quodeq.ai</a>
                  </div>
                  <div className="settings-about-row">
                    <span className="settings-about-key">Repository</span>
                    <a className="settings-about-link" href="https://github.com/quodeq/quodeq" target="_blank" rel="noopener noreferrer">github.com/quodeq/quodeq</a>
                  </div>
                </div>
                {settingsPhrase && (
                  <div className="settings-row settings-row--last settings-about-phrase-row">
                    <span className="settings-about-phrase">{settingsPhrase}</span>
                  </div>
                )}
              </section>
            </div>

            <SettingsAside />
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
            <svg viewBox="288 209 965 588" role="img" aria-label="Quodeq" width="36" height="36" style={{overflow:'visible'}}>
              <defs>
                <filter id="chevron-glow" x="-25%" y="-25%" width="150%" height="150%">
                  <feDropShadow dx="0" dy="0" stdDeviation="6" floodColor="var(--logo-chevron-hover)" floodOpacity="0.28" />
                </filter>
                <mask id="needle-hole-mask">
                  <rect width="1536" height="1024" fill="#fff" />
                  <circle cx="768" cy="502" r="31" fill="#000" />
                </mask>
              </defs>
              <path id="left-chevron" d="M4542 7154 c-29 -14 -68 -45 -87 -68 -18 -22 -109 -135 -201 -251 -92 -115 -229 -286 -304 -380 -75 -93 -262 -327 -415 -520 -153 -192 -299 -375 -323 -405 -62 -77 -84 -125 -90 -195 -6 -79 17 -158 61 -210 18 -22 161 -202 317 -400 156 -198 324 -412 374 -475 131 -165 195 -245 336 -424 237 -301 295 -370 338 -401 l44 -30 255 -3 c288 -3 303 0 303 61 0 32 -21 62 -405 557 -49 63 -159 205 -245 316 -164 213 -528 680 -620 796 -83 106 -100 137 -99 188 0 58 13 86 76 162 28 35 181 225 340 423 158 199 440 550 626 781 247 310 337 428 337 447 0 53 -19 57 -305 57 l-261 0 -52 -26z" transform="translate(0 1024) scale(0.1 -0.1)" style={{fill:'var(--logo-chevron)',cursor:'pointer',transition:'fill 180ms ease, filter 180ms ease'}} />
              <path id="right-chevron" d="M10234 7155 c-19 -19 -23 -31 -18 -48 8 -26 -11 -3 354 -447 155 -190 346 -424 425 -520 137 -170 359 -439 529 -646 92 -110 111 -153 102 -219 -7 -45 -2 -38 -511 -685 -152 -193 -608 -777 -719 -920 -27 -36 -71 -92 -98 -125 -35 -43 -48 -68 -48 -92 0 -60 14 -63 290 -63 244 0 246 0 298 26 28 14 64 40 79 58 31 36 531 667 658 831 44 56 206 261 360 454 154 194 292 371 308 394 34 51 47 97 47 163 0 109 39 55 -653 904 -34 41 -140 172 -236 290 -97 118 -218 267 -269 330 -52 63 -124 152 -160 198 -53 66 -78 89 -126 112 l-59 30 -264 0 -264 0 -25 -25z" transform="translate(0 1024) scale(0.1 -0.1)" style={{fill:'var(--logo-chevron)',cursor:'pointer',transition:'fill 180ms ease, filter 180ms ease'}} />
              <path d="M7347 7895 c-421 -51 -848 -208 -1192 -437 -514 -342 -923 -889 -1083 -1449 -82 -285 -107 -484 -99 -789 6 -255 21 -365 77 -586 50 -195 94 -313 190 -509 212 -432 526 -792 922 -1055 713 -474 1602 -586 2428 -305 89 30 100 31 149 5 166 -84 533 -188 821 -231 158 -24 466 -31 613 -16 l79 9 -39 26 c-104 69 -293 257 -411 409 -90 116 -252 354 -252 370 0 6 6 13 14 16 22 9 237 254 320 366 221 297 383 652 456 996 36 170 50 293 56 485 23 701 -228 1336 -732 1860 -442 458 -1035 753 -1677 835 -145 18 -487 18 -640 0z m643 -551 c628 -93 1210 -469 1534 -994 143 -230 235 -481 283 -769 24 -146 24 -443 -1 -601 -83 -527 -331 -972 -731 -1310 -230 -194 -532 -349 -830 -426 -180 -46 -294 -63 -475 -70 -360 -15 -699 57 -1025 215 -426 208 -750 530 -966 957 -254 505 -298 1067 -122 1594 44 132 153 357 230 475 294 447 746 764 1278 894 249 61 561 74 825 35z" transform="translate(0 1024) scale(0.1 -0.1)" fillRule="evenodd" style={{fill:'var(--logo-q)'}} />
              <g mask="url(#needle-hole-mask)">
                <path d="M 640.21436,652.66711 721.35247,466.18696 899.84338,349.64453 c -87.009,100.60868 -173.29796,201.83295 -259.62902,303.02258 z" style={{fill:'var(--logo-needle)'}} />
                <path d="M 640.21436,652.66711 810.38705,542.33876 899.84338,349.64453 c -87.009,100.60868 -173.29796,201.83295 -259.62902,303.02258 z" style={{fill:'var(--logo-needle-dark)'}} />
              </g>
            </svg>
          </div>
          <span className="sidebar-brand-text">quodeq</span>
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
