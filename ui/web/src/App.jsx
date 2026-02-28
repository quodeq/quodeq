import { useState, useEffect, useMemo } from 'react';
import { listProjects } from './api/index.js';
import { useDashboard } from './features/dashboard/hooks/useDashboard.js';
import DashboardPage from './features/dashboard/components/DashboardPage.jsx';
import RunNavigator from './features/dashboard/components/RunNavigator.jsx';
import { useEvaluation } from './features/evaluation/hooks/useEvaluation.js';
import EvaluationForm from './features/evaluation/components/EvaluationForm.jsx';
import EvaluationStatus from './features/evaluation/components/EvaluationStatus.jsx';
import NavBreadcrumb from './features/explorer/components/NavBreadcrumb.jsx';
import ExplorerPage from './features/explorer/components/ExplorerPage.jsx';
import FileDetailPage from './features/explorer/components/FileDetailPage.jsx';
import PrincipleDetailPage from './features/explorer/components/PrincipleDetailPage.jsx';
import EvalPrincipleDetailPage from './features/explorer/components/EvalPrincipleDetailPage.jsx';
import { formatRunId } from './utils/formatters.js';

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
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M12 2L2 7l10 5 10-5-10-5z" />
    <path d="M2 17l10 5 10-5" />
    <path d="M2 12l10 5 10-5" />
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

  function navPush(entry) { setNavStack((prev) => [...prev, entry]); }
  function navPop() { setNavStack((prev) => (prev.length > 1 ? prev.slice(0, -1) : prev)); }
  function navGoTo(index) { setNavStack((prev) => prev.slice(0, index + 1)); }
  function navReset() { setNavStack([{ page: 'overview' }]); }

  const activePage = navStack[navStack.length - 1];

  // -------------------------------------------------------------------------
  // Project / run selection
  // -------------------------------------------------------------------------
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState('');
  const [selectedRun, setSelectedRun] = useState('latest');

  useEffect(() => {
    listProjects()
      .then((data) => {
        const list = data.projects || data || [];
        setProjects(list);
        if (list.length > 0 && !selectedProject) {
          setSelectedProject(list[0].name || list[0]);
        }
      })
      .catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function handleProjectChange(name) {
    setSelectedProject(name);
    setSelectedRun('latest');
    navReset();
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

  // -------------------------------------------------------------------------
  // Header meta (discipline, repository, source files)
  // -------------------------------------------------------------------------
  const headerMeta = useMemo(() => {
    const dims = accumulated?.dimensions || [];
    if (dims.length === 0) return null;
    const discipline = dims.find((d) => d.discipline)?.discipline ?? null;
    const repository = dims.find((d) => d.repository)?.repository ?? null;
    const totalFiles = dims.reduce((s, d) => s + (d.sourceFileCount || 0), 0);
    return { discipline, repository, totalFiles: totalFiles || null };
  }, [accumulated]);

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
  // Evaluation
  // -------------------------------------------------------------------------
  const { job, jobError, startEvaluation, clearJob } = useEvaluation();

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
  const activeTab = ['overview', 'evaluate', 'settings'].includes(activePage.page)
    ? activePage.page
    : 'overview';

  // Show the project header on all data pages; hide it on evaluate and settings.
  const showProjectHeader = activeTab === 'overview' && projects.length > 0 && !!selectedProject;

  // Show the run navigator only on data pages with runs available.
  const showRunNav = showProjectHeader && availableRuns.length > 0;

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
            onNavigate={handleNavigate}
          />
        );

      case 'evaluate':
        return (
          <section className="evaluate-screen">
            <header className="evaluate-header">
              <div className="evaluate-header-content">
                <div className="evaluate-icon">
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 2L2 7l10 5 10-5-10-5z" />
                    <path d="M2 17l10 5 10-5" />
                    <path d="M2 12l10 5 10-5" />
                  </svg>
                </div>
                <div>
                  <h1>Evaluate Repository</h1>
                  <p className="evaluate-subtitle">Run a comprehensive code quality evaluation on any repository</p>
                </div>
              </div>
            </header>

            <div className="evaluate-content">
              <div className="panel evaluate-panel">
                <div className="panel-header">
                  <h3>Repository Details</h3>
                </div>
                <EvaluationForm onStart={startEvaluation} disabled={job?.status === 'running'} />
              </div>

              {jobError && <div className="job-error-banner">{jobError}</div>}
              <EvaluationStatus job={job} onDismiss={handleEvalDismiss} />

              <div className="panel evaluate-help-panel">
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
              </div>
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
              <h1 className="settings-title">Settings</h1>
            </div>
            <div className="settings-body">
              <section className="settings-section">
                <h2 className="settings-section-title">Appearance</h2>
                <div className="settings-row">
                  <div className="settings-row-label">
                    <span className="settings-label">Theme</span>
                    <span className="settings-description">Choose how CodeCompass looks to you</span>
                  </div>
                  <div className="theme-toggle">
                    {[
                      { value: 'system', label: 'System' },
                      { value: 'light', label: 'Light' },
                      { value: 'dark', label: 'Dark' },
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
            </div>
          </div>
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
          <div className="sidebar-brand-icon">CC</div>
          <span className="sidebar-brand-text">CodeCompass</span>
        </div>

        <nav className="sidebar-nav">
          <button
            type="button"
            className={`sidebar-nav-item${activeTab === 'overview' ? ' active' : ''}`}
            onClick={() => setNavStack([{ page: 'overview' }])}
            title="Overview"
          >
            {ICON_OVERVIEW}
            <span className="sidebar-nav-label">Overview</span>
          </button>

          <button
            type="button"
            className={`sidebar-nav-item${activeTab === 'evaluate' ? ' active' : ''}`}
            onClick={() => setNavStack([{ page: 'evaluate' }])}
            title="Evaluate"
          >
            {ICON_EVALUATE}
            <span className="sidebar-nav-label">Evaluate</span>
          </button>
        </nav>

        {/* Settings at bottom */}
        <div className="sidebar-bottom-nav">
          <button
            type="button"
            className={`sidebar-nav-item${activeTab === 'settings' ? ' active' : ''}`}
            onClick={() => setNavStack([{ page: 'settings' }])}
            title="Settings"
          >
            {ICON_SETTINGS}
            <span className="sidebar-nav-label">Settings</span>
          </button>
        </div>

        {/* Project selector */}
        {projects.length > 0 && (
          <div className="sidebar-project-section">
            <p className="sidebar-project-label">Project</p>
            <select
              className="project-select-styled"
              value={selectedProject}
              disabled={projects.length === 0}
              onChange={(e) => handleProjectChange(e.target.value)}
            >
              {projects.map((p) => {
                const name = p.name || p;
                return <option key={name} value={name}>{name}</option>;
              })}
            </select>
          </div>
        )}
      </aside>

      {/* Main content */}
      <main className="dashboard">
        {/* Persistent project header — shown on all data pages */}
        {showProjectHeader && (
          <header className="content-header">
            <div className="content-header-left">
              <h1 className="content-project-name">{selectedProject}</h1>
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
                currentRun={formatRunId(currentOverviewRun)}
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
