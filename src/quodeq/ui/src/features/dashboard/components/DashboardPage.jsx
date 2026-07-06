import { useEffect, useMemo, useRef, useState } from 'react';
import DimensionCard from './DimensionCard.jsx';
import AccumulatedOverviewPanel from './AccumulatedOverviewPanel.jsx';
import RunOverviewPanel from './RunOverviewPanel.jsx';
import IncompleteSetupCard from './IncompleteSetupCard.jsx';
import LoadingScreen from '../../../components/LoadingScreen.jsx';
import EmptyState from '../../../components/EmptyState.jsx';

function NoCompletedEvalPanel({ availableRuns = [], onNavigate }) {
  const hasRunning = availableRuns.some((r) => r?.status === 'in_progress');
  if (hasRunning) {
    // First-ever evaluation is still running. There's no prior data to
    // show, but we still avoid claiming the project has "no" evaluations
    // — they just haven't finished yet.
    return (
      <EmptyState
        title="First evaluation in progress"
        description="The overview will fill in once a run finishes. You can watch dimensions complete in History."
        actionLabel="Open history"
        onAction={() => onNavigate?.('history')}
      />
    );
  }
  return (
    <EmptyState
      title="No completed evaluation yet"
      description="Previous attempts didn't finish cleanly. Start a new evaluation to populate the overview."
      actionLabel="Start evaluation"
      onAction={() => onNavigate?.('evaluate')}
    />
  );
}

function DashboardContent({ runMode, data, focus, callbacks }) {
  const { dashboard, selectedRunId, accumulated, accumulatedDimensions, availableRuns, dailyRuns, overviewRunIndex, selectedProject, projectInfo, granularity } = data;
  const { dimension: focusedDimension, setDimension: setFocusedDimension, dimensionData: focusedDimensionData } = focus;
  const { onRunSelect, onDimensionCardClick, onAccumulatedDimensionClick, onFileClick, onNavigate, onGranularityChange } = callbacks;
  if (runMode) {
    return (
      <RunOverviewPanel
        dashboard={dashboard}
        selectedRunId={selectedRunId}
        projectName={projectInfo?.displayName || projectInfo?.name || selectedProject}
        onDimensionClick={onDimensionCardClick}
        onFileClick={onFileClick}
        onNavigate={onNavigate}
      />
    );
  }
  if (!accumulated) {
    return <LoadingScreen />;
  }
  if (accumulatedDimensions.length === 0) {
    // Project has runs (otherwise the upstream `!dashboard` empty
    // state would have fired) but none have terminated cleanly yet —
    // first evaluation in progress, or every prior attempt was
    // cancelled/failed. Render a clear waiting-for-results state in
    // place of the empty stat strip and dim cards (the page header
    // above still shows project name, language mix, file count).
    return <NoCompletedEvalPanel availableRuns={availableRuns} onNavigate={onNavigate} />;
  }
  if (focusedDimension) {
    return (
      <div className="dimensions-panel">
        <div className="section-header">
          <h3 className="section-title">{focusedDimension}</h3>
          <button type="button" className="btn-secondary" onClick={() => setFocusedDimension(null)}>
            Show all
          </button>
        </div>
        <DimensionCard title={focusedDimension} dimension={focusedDimensionData} isSingleFocus={true} />
      </div>
    );
  }
  return (
    <AccumulatedOverviewPanel
      data={{
        accumulated: accumulated ? { ...accumulated, dimensions: accumulatedDimensions } : accumulated,
        accumulatedDimensions, availableRuns, dailyRuns, overviewRunIndex,
        trend: dashboard?.trend || [], selectedRunId, selectedProject, projectInfo, granularity,
      }}
      callbacks={{
        onRunClick: onRunSelect, onDimensionClick: onAccumulatedDimensionClick, onNavigate, onGranularityChange,
      }}
    />
  );
}

// ---------------------------------------------------------------------------
// DashboardPage — body only, header is rendered by App.jsx
// Top-level page component that receives all dashboard state and callbacks
// directly from App; the high prop count is intentional and not worth splitting.
// ---------------------------------------------------------------------------

function useDashboardHandlers(onNavigate, dashboard) {
  return useMemo(() => ({
    handleDimensionCardClick: (item, runId) => {
      if (!onNavigate) return;
      const dateLabel = dashboard?.selectedRun?.dateLabel || item.fromDateLabel;
      onNavigate('explorer', { dimension: item.dimension, runId: runId || item.fromRunId, dateLabel, fromProject: item.fromProject });
    },
    handleAccumulatedDimensionClick: (item) => {
      if (onNavigate) onNavigate('explorer', { dimension: item.dimension, runId: item.fromRunId, dateLabel: item.fromDateLabel, fromProject: item.fromProject });
    },
    handleFileClick: (fileObj) => { if (onNavigate) onNavigate('file', { file: fileObj }); },
  }), [onNavigate, dashboard]);
}

export default function DashboardPage({ data = {}, callbacks = {}, runMode = false }) {
  const { selectedProject, selectedRun, projects = [], dashboard, accumulated, loading, isFetching, error, availableRuns = [], dailyRuns, overviewRunIndex = 0, granularity = 'day', onGranularityChange } = data;
  const projectInfo = projects.find((p) => (p.id || p.name) === selectedProject) || null;
  const { onNavigate, onRunSelect, onProjectsReload } = callbacks;
  // After a successful clone-on-add migration the project's repository_info.json
  // has been rewritten with location: "local". Refetch the projects list so the
  // sidebar/header reflect the new state. Fall back to a full reload if no
  // refetch hook is plumbed through.
  const handleSetupComplete = () => {
    if (typeof onProjectsReload === 'function') onProjectsReload();
    else if (typeof window !== 'undefined') window.location.reload();
  };
  const [focusedDimension, setFocusedDimension] = useState(null);
  const selectedRunId = dashboard?.selectedRun?.runId || selectedRun;
  // Clear focused dimension when the active run changes to avoid showing stale data
  const prevRunRef = useRef(selectedRunId);
  useEffect(() => {
    if (prevRunRef.current !== selectedRunId) {
      prevRunRef.current = selectedRunId;
      setFocusedDimension(null);
    }
  }, [selectedRunId]);
  // Accumulated dimensions are pre-rescored from the server — no client-side merge needed
  const accumulatedDimensions = useMemo(() => accumulated?.dimensions || [], [accumulated]);
  const focusedDimensionData = useMemo(() => focusedDimension ? (dashboard?.dimensions || []).find((d) => d.dimension === focusedDimension) || null : null, [focusedDimension, dashboard]);
  const handlers = useDashboardHandlers(onNavigate, dashboard);

  // What each view needs before it can render real content: run detail only
  // needs the dashboard payload; the Overview also needs the scores-derived
  // `accumulated` block (DashboardContent returns a LoadingScreen without it).
  // These hooks MUST stay above the early returns below — calling them after a
  // conditional return changes the hook count between renders (React error
  // #310, a blank-crash on load).
  const contentReady = runMode ? !!dashboard : (!!dashboard && !!accumulated);
  // Grace state for the slow/cold-load fallback (consumed by isLoading below).
  const [graceElapsed, setGraceElapsed] = useState(false);
  useEffect(() => {
    if (contentReady || !dashboard) { setGraceElapsed(false); return undefined; }
    const timer = setTimeout(() => setGraceElapsed(true), 700);
    return () => clearTimeout(timer);
  }, [contentReady, dashboard]);

  const { projectsLoaded } = data;
  if (!projectsLoaded) return <LoadingScreen />;
  if (projects.length === 0) {
    return (
      <EmptyState
        title="No projects yet"
        description="Add a project to start analyzing code quality."
        actionLabel="Add a project"
        onAction={() => onNavigate?.('projects')}
      />
    );
  }
  if (!selectedProject) {
    return (
      <EmptyState
        title="No project selected"
        description="Pick a project to view its overview."
        actionLabel="Choose project"
        onAction={() => onNavigate?.('projects')}
      />
    );
  }
  if (!loading && !isFetching && !dashboard) {
    const projectName = projectInfo?.displayName || projectInfo?.name || selectedProject;
    return (
      <div className="dashboard-page dashboard-fade dashboard-ready">
        <IncompleteSetupCard projectInfo={projectInfo} onComplete={handleSetupComplete} />
        <EmptyState
          title="No evaluations yet"
          description={`Run an evaluation for ${projectName} to populate this page.`}
          actionLabel="Start evaluation"
          onAction={() => onNavigate?.('evaluate')}
        />
      </div>
    );
  }

  // Hold the full LoadingScreen until the content is ready, so we don't fade in
  // a half-drawn page and then pop the real content in a beat later (the
  // first-load flicker). BUT a cold score cache can take several seconds to
  // rebuild (e.g. right after a dismiss/restore/formula change invalidates it);
  // sitting on a blank spinner that whole time reads as "not opening". So once
  // the dashboard payload is in and the grace has elapsed (graceElapsed, set
  // above), fall back to the partial page (frame + a content spinner) so a slow
  // load shows progress instead of a hang. The grace comfortably exceeds a warm
  // load, so the fast path still gets one clean transition.
  const isLoading = loading && !contentReady && !(dashboard && graceElapsed);
  // True while a *background* fetch is running but we're already showing
  // data (placeholderData kept the previous run on screen during a switch).
  // The page dims itself slightly so the user sees "still working" without
  // the jarring full-screen LoadingScreen.
  const isRefreshing = isFetching && !!dashboard && !isLoading;
  return (
    <div className={`dashboard-page dashboard-fade ${isLoading ? 'dashboard-loading' : 'dashboard-ready'}${isRefreshing ? ' dashboard-refreshing' : ''}`}>
      <IncompleteSetupCard projectInfo={projectInfo} onComplete={handleSetupComplete} />
      {error && <p className="inline-error">Failed to load dashboard data. Please try again.</p>}
      {isLoading && <LoadingScreen />}
      {dashboard && (
        <DashboardContent
          runMode={runMode}
          data={{ dashboard, selectedRunId, accumulated, accumulatedDimensions, availableRuns, dailyRuns, overviewRunIndex, selectedProject, projectInfo, granularity }}
          focus={{ dimension: focusedDimension, setDimension: setFocusedDimension, dimensionData: focusedDimensionData }}
          callbacks={{ onRunSelect, onDimensionCardClick: handlers.handleDimensionCardClick, onAccumulatedDimensionClick: handlers.handleAccumulatedDimensionClick, onFileClick: handlers.handleFileClick, onNavigate, onGranularityChange }}
        />
      )}
    </div>
  );
}
