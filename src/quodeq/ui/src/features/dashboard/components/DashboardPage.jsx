import { useMemo, useState } from 'react';
import DimensionCard from './DimensionCard.jsx';
import AccumulatedOverviewPanel from './AccumulatedOverviewPanel.jsx';
import RunOverviewPanel from './RunOverviewPanel.jsx';

function DashboardContent({ runMode, data, focus, callbacks }) {
  const { dashboard, selectedRunId, accumulated, accumulatedDimensions, availableRuns, dailyRuns, overviewRunIndex } = data;
  const { dimension: focusedDimension, setDimension: setFocusedDimension, dimensionData: focusedDimensionData } = focus;
  const { onRunSelect, onDimensionCardClick, onAccumulatedDimensionClick, onFileClick } = callbacks;
  if (runMode) {
    return (
      <RunOverviewPanel
        dashboard={dashboard}
        selectedRunId={selectedRunId}
        onDimensionClick={onDimensionCardClick}
        onFileClick={onFileClick}
      />
    );
  }
  if (!accumulated) {
    return <p className="empty-state">Loading accumulated data...</p>;
  }
  if (focusedDimension) {
    return (
      <div className="dimensions-panel">
        <div className="dimensions-header">
          <h3 className="dimensions-title">{focusedDimension}</h3>
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
        accumulated, accumulatedDimensions, availableRuns, dailyRuns, overviewRunIndex,
        trend: dashboard?.trend || [], selectedRunId,
      }}
      callbacks={{
        onRunClick: onRunSelect, onDimensionClick: onAccumulatedDimensionClick,
      }}
    />
  );
}

// ---------------------------------------------------------------------------
// DashboardPage — body only, header is rendered by App.jsx
// Top-level page component that receives all dashboard state and callbacks
// directly from App; the high prop count is intentional and not worth splitting.
// ---------------------------------------------------------------------------

function makeDashboardHandlers(onNavigate, dashboard) {
  return {
    handleDimensionCardClick: (item, runId) => {
      if (onNavigate) {
        const dateLabel = dashboard?.selectedRun?.dateLabel || item.fromDateLabel;
        onNavigate('explorer', { dimension: item.dimension, runId: runId || item.fromRunId, dateLabel });
      }
    },
    handleAccumulatedDimensionClick: (item) => {
      if (onNavigate) onNavigate('explorer', { dimension: item.dimension, runId: item.fromRunId, dateLabel: item.fromDateLabel });
    },
    handleFileClick: (fileObj) => { if (onNavigate) onNavigate('file', { file: fileObj }); },
  };
}

export default function DashboardPage({ data = {}, callbacks = {}, runMode = false }) {
  const {
    selectedProject, selectedRun, projects = [],
    dashboard, accumulated, loading, error,
    availableRuns = [], dailyRuns, overviewRunIndex = 0,
  } = data;
  const { onNavigate, onRunSelect } = callbacks;
  const [focusedDimension, setFocusedDimension] = useState(null);
  const selectedRunId = dashboard?.selectedRun?.runId || selectedRun;
  const accumulatedDimensions = accumulated?.dimensions || [];
  const focusedDimensionData = useMemo(() => {
    if (!focusedDimension) return null;
    return (dashboard?.dimensions || []).find((d) => d.dimension === focusedDimension) || null;
  }, [focusedDimension, dashboard]);
  const handlers = makeDashboardHandlers(onNavigate, dashboard);

  if (!projects || projects.length === 0) {
    return <section className="empty-state"><h2>No analyzed projects yet</h2><p>Run an evaluation to get started.</p></section>;
  }

  return (
    <div className="dashboard-page">
      {error && <p className="inline-error">Failed to load dashboard data. Please try again.</p>}
      {loading && !dashboard && <p className="loading" role="status" aria-live="polite">Loading dashboard...</p>}
      {dashboard && (
        <DashboardContent
          runMode={runMode}
          data={{ dashboard, selectedRunId, accumulated, accumulatedDimensions, availableRuns, dailyRuns, overviewRunIndex }}
          focus={{ dimension: focusedDimension, setDimension: setFocusedDimension, dimensionData: focusedDimensionData }}
          callbacks={{ onRunSelect, onDimensionCardClick: handlers.handleDimensionCardClick, onAccumulatedDimensionClick: handlers.handleAccumulatedDimensionClick, onFileClick: handlers.handleFileClick }}
        />
      )}
    </div>
  );
}
