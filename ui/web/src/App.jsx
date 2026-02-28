import { useState, useEffect } from 'react';
import { listProjects } from './api/index.js';
import DashboardPage from './features/dashboard/components/DashboardPage.jsx';
import { useEvaluation } from './features/evaluation/hooks/useEvaluation.js';
import EvaluationForm from './features/evaluation/components/EvaluationForm.jsx';
import EvaluationStatus from './features/evaluation/components/EvaluationStatus.jsx';
import NavBreadcrumb from './features/explorer/components/NavBreadcrumb.jsx';
import FileDetailPage from './features/explorer/components/FileDetailPage.jsx';
import PrincipleDetailPage from './features/explorer/components/PrincipleDetailPage.jsx';
import EvalPrincipleDetailPage from './features/explorer/components/EvalPrincipleDetailPage.jsx';

export default function App() {
  // -------------------------------------------------------------------------
  // Nav stack state
  // -------------------------------------------------------------------------
  const [navStack, setNavStack] = useState([{ page: 'overview' }]);

  function navPush(entry) {
    setNavStack((prev) => [...prev, entry]);
  }

  function navPop() {
    setNavStack((prev) => (prev.length > 1 ? prev.slice(0, -1) : prev));
  }

  function navGoTo(index) {
    setNavStack((prev) => prev.slice(0, index + 1));
  }

  function navReset() {
    setNavStack([{ page: 'overview' }]);
  }

  const activePage = navStack[navStack.length - 1];

  // -------------------------------------------------------------------------
  // Project / run selection state
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

  function handleRunChange(runId) {
    setSelectedRun(runId);
  }

  // -------------------------------------------------------------------------
  // Sidebar state
  // -------------------------------------------------------------------------
  const [sidebarExpanded, setSidebarExpanded] = useState(true);

  // -------------------------------------------------------------------------
  // Evaluation feature state (hook lives here so it survives tab switches)
  // -------------------------------------------------------------------------
  const { job, jobError, startEvaluation, clearJob } = useEvaluation();

  function handleEvalDismiss(action) {
    if (action === 'view') {
      navPush({ page: 'overview' });
    }
    clearJob();
  }

  // -------------------------------------------------------------------------
  // Navigation handler passed to child features
  // -------------------------------------------------------------------------
  function handleNavigate(page, params = {}) {
    navPush({ page, ...params });
  }

  // -------------------------------------------------------------------------
  // Sidebar tab entries
  // -------------------------------------------------------------------------
  const NAV_TABS = [
    { page: 'overview', label: 'Overview' },
    { page: 'evaluate', label: 'Evaluate' },
  ];

  // -------------------------------------------------------------------------
  // Render active feature content
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
            onProjectChange={handleProjectChange}
            onRunChange={handleRunChange}
            onNavigate={handleNavigate}
          />
        );

      case 'evaluate':
        return (
          <div className="evaluate-page">
            <EvaluationForm
              onStart={startEvaluation}
              disabled={job?.status === 'running'}
            />
            {jobError && (
              <div className="job-error-banner">{jobError}</div>
            )}
            <EvaluationStatus job={job} onDismiss={handleEvalDismiss} />
          </div>
        );

      case 'file-detail':
        return <FileDetailPage file={params.file} />;

      case 'principle-detail':
        return <PrincipleDetailPage principle={params.principle} />;

      case 'eval-principle-detail':
        return <EvalPrincipleDetailPage evalPrincipal={params.evalPrincipal} />;

      default:
        return (
          <div className="page-not-found">
            <p>Page not found: {page}</p>
          </div>
        );
    }
  }

  // -------------------------------------------------------------------------
  // Layout
  // -------------------------------------------------------------------------
  const activeTab = ['overview', 'evaluate'].includes(activePage.page)
    ? activePage.page
    : 'overview';

  return (
    <div className={`app-layout${sidebarExpanded ? '' : ' sidebar-collapsed'}`}>
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-top">
          <button
            className="sidebar-toggle"
            onClick={() => setSidebarExpanded((v) => !v)}
            title={sidebarExpanded ? 'Collapse sidebar' : 'Expand sidebar'}
            aria-label={sidebarExpanded ? 'Collapse sidebar' : 'Expand sidebar'}
          >
            {sidebarExpanded ? '‹' : '›'}
          </button>
        </div>

        <nav className="sidebar-nav">
          {NAV_TABS.map(({ page, label }) => (
            <button
              key={page}
              className={`sidebar-tab${activeTab === page ? ' active' : ''}`}
              onClick={() => {
                navReset();
                setNavStack([{ page }]);
              }}
              title={label}
              aria-label={label}
            >
              <span className="sidebar-tab-label">{label}</span>
            </button>
          ))}
        </nav>
      </aside>

      {/* Main content */}
      <main className="main-content">
        {navStack.length > 1 && (
          <NavBreadcrumb
            stack={navStack}
            onBack={navPop}
            onGoTo={navGoTo}
          />
        )}
        {renderContent()}
      </main>
    </div>
  );
}
