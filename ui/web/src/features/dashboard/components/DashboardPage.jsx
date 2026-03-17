import { useMemo, useState } from 'react';
import DimensionCard from './DimensionCard.jsx';
import AccumulatedOverviewPanel from './AccumulatedOverviewPanel.jsx';
import RunOverviewPanel from './RunOverviewPanel.jsx';

// ---------------------------------------------------------------------------
// DashboardPage — body only, header is rendered by App.jsx
// ---------------------------------------------------------------------------

export default function DashboardPage({
  selectedProject,
  selectedRun,
  projects = [],
  onNavigate,
  onRunSelect,
  runMode = false,
  // Data from App-level useDashboard
  dashboard,
  accumulated,
  loading,
  error,
  availableRuns = [],
  overviewRunIndex = 0,
}) {
  const [focusedDimension, setFocusedDimension] = useState(null);

  const selectedRunId = dashboard?.selectedRun?.runId || selectedRun;
  const accumulatedDimensions = accumulated?.dimensions || [];

  const focusedDimensionData = useMemo(() => {
    if (!focusedDimension) return null;
    return (dashboard?.dimensions || []).find((d) => d.dimension === focusedDimension) || null;
  }, [focusedDimension, dashboard]);

  const handleDimensionCardClick = (item, runId) => {
    if (onNavigate) {
      const dateLabel = dashboard?.selectedRun?.dateLabel || item.fromDateLabel;
      onNavigate('explorer', { dimension: item.dimension, runId: runId || item.fromRunId, dateLabel });
    }
  };

  const handleAccumulatedDimensionClick = (item) => {
    if (onNavigate) {
      onNavigate('explorer', { dimension: item.dimension, runId: item.fromRunId, dateLabel: item.fromDateLabel });
    }
  };

  const handleFileClick = (fileObj) => {
    if (onNavigate) onNavigate('file', { file: fileObj });
  };

  const handlePrincipleClick = (principleObj) => {
    if (onNavigate) onNavigate('principle', { principle: principleObj });
  };

  if (!projects || projects.length === 0) {
    return (
      <section className="empty-state">
        <h2>No analyzed projects yet</h2>
        <p>Run an evaluation to get started.</p>
      </section>
    );
  }

  return (
    <div className="dashboard-page">
      {error && <p className="inline-error">{error}</p>}
      {loading && <p className="loading" role="status" aria-live="polite">Loading dashboard...</p>}

      {!loading && dashboard && (
        <>
          {runMode ? (
            <RunOverviewPanel
              dashboard={dashboard}
              selectedRunId={selectedRunId}
              onDimensionClick={handleDimensionCardClick}
              onFileClick={handleFileClick}
            />
          ) : accumulated ? (
            <>
              {focusedDimension ? (
                <div className="dimensions-panel">
                  <div className="dimensions-header">
                    <h3 className="dimensions-title">{focusedDimension}</h3>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => setFocusedDimension(null)}
                    >
                      Show all
                    </button>
                  </div>
                  <DimensionCard
                    title={focusedDimension}
                    dimension={focusedDimensionData}
                    isSingleFocus={true}
                  />
                </div>
              ) : (
                <AccumulatedOverviewPanel
                  accumulated={accumulated}
                  accumulatedDimensions={accumulatedDimensions}
                  availableRuns={availableRuns}
                  overviewRunIndex={overviewRunIndex}
                  trend={dashboard?.trend || []}
                  selectedRunId={selectedRunId}
                  onRunClick={onRunSelect}
                  onDimensionClick={handleAccumulatedDimensionClick}
                  onFileClick={handleFileClick}
                  onPrincipleClick={handlePrincipleClick}
                />
              )}
            </>
          ) : (
            <p className="empty-state">Loading accumulated data...</p>
          )}
        </>
      )}

    </div>
  );
}
