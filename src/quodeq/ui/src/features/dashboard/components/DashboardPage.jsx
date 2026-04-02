import { useMemo, useState } from 'react';
import DimensionCard from './DimensionCard.jsx';
import AccumulatedOverviewPanel from './AccumulatedOverviewPanel.jsx';
import RunOverviewPanel from './RunOverviewPanel.jsx';
import LoadingScreen from '../../../components/LoadingScreen.jsx';

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
    return <LoadingScreen />;
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
        accumulated: accumulated ? { ...accumulated, dimensions: accumulatedDimensions } : accumulated,
        accumulatedDimensions, availableRuns, dailyRuns, overviewRunIndex,
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

function useDashboardHandlers(onNavigate, dashboard) {
  return useMemo(() => ({
    handleDimensionCardClick: (item, runId) => {
      if (!onNavigate) return;
      const dateLabel = dashboard?.selectedRun?.dateLabel || item.fromDateLabel;
      onNavigate('explorer', { dimension: item.dimension, runId: runId || item.fromRunId, dateLabel });
    },
    handleAccumulatedDimensionClick: (item) => {
      if (onNavigate) onNavigate('explorer', { dimension: item.dimension, runId: item.fromRunId, dateLabel: item.fromDateLabel });
    },
    handleFileClick: (fileObj) => { if (onNavigate) onNavigate('file', { file: fileObj }); },
  }), [onNavigate, dashboard]);
}

export default function DashboardPage({ data = {}, callbacks = {}, runMode = false }) {
  const { selectedProject, selectedRun, projects = [], dashboard, accumulated, rescoreLookup = {}, loading, error, availableRuns = [], dailyRuns, overviewRunIndex = 0 } = data;
  const { onNavigate, onRunSelect } = callbacks;
  const [focusedDimension, setFocusedDimension] = useState(null);
  const selectedRunId = dashboard?.selectedRun?.runId || selectedRun;
  // Merge rescored grades into accumulated dimensions so all cards reflect live scores
  const accumulatedDimensions = useMemo(() => {
    const dims = accumulated?.dimensions || [];
    if (Object.keys(rescoreLookup).length === 0) return dims;
    return dims.map((dim) => {
      const match = rescoreLookup[(dim.dimension || '').toLowerCase()];
      if (!match) return dim;
      return { ...dim, overallScore: match.overallScore, overallGrade: match.overallGrade, totals: match.totals ?? dim.totals };
    });
  }, [accumulated, rescoreLookup]);
  const focusedDimensionData = useMemo(() => focusedDimension ? (dashboard?.dimensions || []).find((d) => d.dimension === focusedDimension) || null : null, [focusedDimension, dashboard]);
  const handlers = useDashboardHandlers(onNavigate, dashboard);

  if (!projects || projects.length === 0) {
    if (loading) return <LoadingScreen />;
    return <section className="empty-state"><h2>No analyzed projects yet</h2><p>Run an evaluation to get started.</p></section>;
  }

  return (
    <div className="dashboard-page">
      {error && <p className="inline-error">Failed to load dashboard data. Please try again.</p>}
      {loading && !dashboard && <LoadingScreen />}
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
