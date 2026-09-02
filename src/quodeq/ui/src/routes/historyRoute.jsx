/**
 * The History tab's route renderer, moved out of routes/renderers.jsx
 * verbatim (move-only refactor).
 */
import { lazy } from 'react';

const HistoryPage = lazy(() => import('../features/history/components/HistoryPage.jsx'));

function resolveHistorySelectedRunId(selectedRun, trend) {
  if (selectedRun && selectedRun !== 'latest' && trend.some((t) => t.runId === selectedRun)) return selectedRun;
  return trend.length > 0 ? trend[0].runId : null;
}

export function historyRoute(params, props) {
  const trend = props.dashboardData.dashboard?.trend || [];
  const runs = props.dashboardData.availableRuns || [];
  return (
    <HistoryPage
      trend={trend}
      selection={{
        selectedRunId: resolveHistorySelectedRunId(props.navigation.historySelectedRun, trend),
        selectedRunScore: props.dashboardData.accumulated?.summary?.numericAverage,
      }}
      availableRuns={runs}
      dimensions={{
        accumulatedDimensions: props.dashboardData.accumulated?.dimensions || [],
        lastRun: { date: props.dashboardData.accumulated?.dimensions?.[0]?.fromDateLabel, runId: props.dashboardData.accumulated?.dimensions?.[0]?.fromRunId },
      }}
      callbacks={{
        onRunClick: (runId, dateLabel) => props.navigation.handleNavigate('history-run', { runId, dateLabel }),
        onDimensionClick: (dim) => props.navigation.handleNavigate('explorer', { dimension: dim.dimension, runId: dim.fromRunId, dateLabel: dim.fromDateLabel, fromProject: dim.fromProject }),
        onNavigate: props.navigation.handleNavigate,
        onRunChange: props.navigation.setHistorySelectedRun,
        // Run deletion changes the accumulated rollup the Overview grade is
        // built from — same mutation class as dismiss/restore, so it gets
        // the same debounced ACTIVE reconcile (mark-stale alone never
        // reaches the always-mounted Overview observer).
        onRunDeleted: () => props.scheduleDashboardReconcile?.(),
      }}
      projects={props.navigation.projects}
      projectsLoaded={props.navigation.projectsLoaded}
      selectedProject={props.navigation.selectedProject}
      selectedSource={props.navigation.selectedSource}
      loading={props.dashboardData.loading}
      isFetching={props.dashboardData.isFetching}
      error={props.dashboardData.error}
      onRetry={props.dashboardData.onRetry}
      projectInfo={props.navigation.projects?.find((p) => (p.id || p.name) === props.navigation.selectedProject) || null}
    />
  );
}
