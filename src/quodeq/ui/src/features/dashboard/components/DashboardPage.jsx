import { useEffect, useMemo, useRef, useState } from 'react';
import DimensionCard from './DimensionCard.jsx';
import AccumulatedOverviewPanel from './AccumulatedOverviewPanel.jsx';
import RunOverviewPanel from './RunOverviewPanel.jsx';
import LoadingScreen from '../../../components/LoadingScreen.jsx';
import EmptyState from '../../../components/EmptyState.jsx';

function DashboardContent({ runMode, data, focus, callbacks }) {
  const { dashboard, selectedRunId, accumulated, accumulatedDimensions, availableRuns, dailyRuns, overviewRunIndex, selectedProject, projectInfo } = data;
  const { dimension: focusedDimension, setDimension: setFocusedDimension, dimensionData: focusedDimensionData } = focus;
  const { onRunSelect, onDimensionCardClick, onAccumulatedDimensionClick, onFileClick, onNavigate } = callbacks;
  if (runMode) {
    return (
      <RunOverviewPanel
        dashboard={dashboard}
        selectedRunId={selectedRunId}
        projectName={projectInfo?.displayName || projectInfo?.name || selectedProject}
        onDimensionClick={onDimensionCardClick}
        onFileClick={onFileClick}
      />
    );
  }
  if (!accumulated) {
    return <LoadingScreen />;
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
        trend: dashboard?.trend || [], selectedRunId, selectedProject, projectInfo,
      }}
      callbacks={{
        onRunClick: onRunSelect, onDimensionClick: onAccumulatedDimensionClick, onNavigate,
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
  const { selectedProject, selectedRun, projects = [], dashboard, accumulated, loading, isFetching, error, availableRuns = [], dailyRuns, overviewRunIndex = 0 } = data;
  const projectInfo = projects.find((p) => (p.id || p.name) === selectedProject) || null;
  const { onNavigate, onRunSelect } = callbacks;
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

  const { projectsLoaded } = data;
  if (!projectsLoaded) return <LoadingScreen />;
  if (projects.length === 0) {
    return (
      <EmptyState
        title="No projects yet"
        description="Run your first evaluation to start analyzing code quality."
        actionLabel="Start evaluating"
        onAction={() => onNavigate?.('evaluate')}
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
      <EmptyState
        title="No evaluations yet"
        description={`Run an evaluation for ${projectName} to populate this page.`}
        actionLabel="Start evaluation"
        onAction={() => onNavigate?.('evaluate')}
      />
    );
  }

  const isLoading = loading && !dashboard;
  // True while a *background* fetch is running but we're already showing
  // data (placeholderData kept the previous run on screen during a switch).
  // The page dims itself slightly so the user sees "still working" without
  // the jarring full-screen LoadingScreen.
  const isRefreshing = isFetching && !!dashboard && !isLoading;

  return (
    <div className={`dashboard-page dashboard-fade ${isLoading ? 'dashboard-loading' : 'dashboard-ready'}${isRefreshing ? ' dashboard-refreshing' : ''}`}>
      {error && <p className="inline-error">Failed to load dashboard data. Please try again.</p>}
      {isLoading && <LoadingScreen />}
      {dashboard && (
        <DashboardContent
          runMode={runMode}
          data={{ dashboard, selectedRunId, accumulated, accumulatedDimensions, availableRuns, dailyRuns, overviewRunIndex, selectedProject, projectInfo }}
          focus={{ dimension: focusedDimension, setDimension: setFocusedDimension, dimensionData: focusedDimensionData }}
          callbacks={{ onRunSelect, onDimensionCardClick: handlers.handleDimensionCardClick, onAccumulatedDimensionClick: handlers.handleAccumulatedDimensionClick, onFileClick: handlers.handleFileClick, onNavigate }}
        />
      )}
    </div>
  );
}
