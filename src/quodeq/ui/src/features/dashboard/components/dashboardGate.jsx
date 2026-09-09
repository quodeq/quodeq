import {
  NoLocalProjectsSharedContent, NoProjectsContent, NoProjectSelectedContent,
  LoadingProjectContent, LoadProjectFailedContent, NoRunsEmptyContent, RunLoadFailedContent,
} from './DashboardPageEmptyStates.jsx';

// The early-return ladder of DashboardPage, as plain functions and not as
// components: DashboardPage.fadeOnceIdentity.test.jsx pins the .dashboard-page
// DOM node's identity across branch transitions, and a component boundary here
// would give each branch its own fiber, so every swap would remount the node.
// Called from the same position in DashboardPage's render, these return the
// exact element tree the branches returned inline.
//
// The leading {null} in every fragment is load-bearing: it holds the sibling
// slot the main branch fills with the inline LoadingScreen, keeping the <div>
// at child index 1 in every branch so React reconciles it as the same node.
function gateFrame(className, children) {
  return (
    <>
      {null}
      <div className={className}>{children}</div>
    </>
  );
}

export function dashboardPageClassName({ appearClass = '', dimmed = false, refreshing = false }) {
  const state = dimmed ? 'dashboard-loading' : `dashboard-ready${appearClass}`;
  return `dashboard-page dashboard-fade ${state}${refreshing ? ' dashboard-refreshing' : ''}`;
}

function renderNoProjectsGate({ sharedHasContent, onNavigate, readyClass }) {
  // Zero local projects. When the connected shared repo has published
  // content, the useful next step is browsing it (read-only until pulled)
  // -- not necessarily scanning something locally. Both CTAs land on the
  // repositories tab; the copy is what differs.
  if (sharedHasContent) {
    return gateFrame(readyClass, <NoLocalProjectsSharedContent onNavigate={onNavigate} />);
  }
  return gateFrame(readyClass, <NoProjectsContent onNavigate={onNavigate} />);
}

function renderProjectErrorGate({ isFetching, projectName, error, onRetry, readyClass }) {
  // A failed fetch also lands here (dashboard === null, queries settled).
  // It must render as an error: claiming "No evaluations yet" on a
  // 404/500/timeout tells the user their existing evaluations are gone.
  // While a retry is in flight (error still set, isFetching true), show
  // the loader instead so clicking Retry visibly does something.
  if (isFetching) {
    return gateFrame(readyClass, <LoadingProjectContent projectName={projectName} />);
  }
  return gateFrame(readyClass, <LoadProjectFailedContent error={error} onRetry={onRetry} />);
}

function renderRunModeGate({ isFetching, projectName, onRetry, readyClass }) {
  // createDashboard passes a falsy raw response through unchanged rather
  // than throwing (models/dashboard.js), so "settled, no error, no
  // dashboard" is a valid non-error outcome, not just a theoretical one --
  // this run's data didn't come back. Without this branch it fell through
  // every other check (all gated on runMode being false, or on dashboard
  // being truthy) to a genuinely blank .dashboard-page.
  if (isFetching) {
    return gateFrame(readyClass, <LoadingProjectContent projectName={projectName} />);
  }
  return gateFrame(readyClass, <RunLoadFailedContent onRetry={onRetry} />);
}

// Returns null when no gate applies and the body should render; every branch
// that does apply returns a fragment, so the caller tests the result directly.
export function renderDashboardGate({ data, callbacks, runMode, projectName, projectInfo, pageState, onSetupComplete }) {
  const { projects = [], selectedSource, sharedHasContent = false, selectedProject, dashboard, loading, error, isFetching } = data;
  const { onNavigate, onRetry } = callbacks;
  const readyClass = dashboardPageClassName({ appearClass: pageState.dashboardAppearClass });
  if (projects.length === 0 && selectedSource !== 'shared') {
    return renderNoProjectsGate({ sharedHasContent, onNavigate, readyClass });
  }
  if (!selectedProject) {
    return gateFrame(readyClass, <NoProjectSelectedContent onNavigate={onNavigate} />);
  }
  if (!loading && !dashboard && error) {
    return renderProjectErrorGate({ isFetching, projectName, error, onRetry, readyClass });
  }
  if (pageState.showNoRunsEmpty) {
    const refreshingClass = dashboardPageClassName({ appearClass: pageState.dashboardAppearClass, refreshing: isFetching });
    return gateFrame(refreshingClass, <NoRunsEmptyContent projectInfo={projectInfo} onComplete={onSetupComplete} projectName={projectName} onNavigate={onNavigate} />);
  }
  if (runMode && !loading && !dashboard && !error) {
    return renderRunModeGate({ isFetching, projectName, onRetry, readyClass });
  }
  return null;
}
