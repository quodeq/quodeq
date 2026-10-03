/**
 * The History tab's route renderer.
 */
import { lazy } from 'react';
import { LATEST_RUN_ID } from '../constants.js';
import { NAV_TAB } from '../vocab/navTab.js';
import { findProject } from '../utils/projectIdentity.js';

const HistoryPage = lazy(() => import('../features/history/components/HistoryPage.jsx'));

function resolveHistorySelectedRunId(selectedRun, trend) {
  if (selectedRun && selectedRun !== LATEST_RUN_ID && trend.some((t) => t.runId === selectedRun)) return selectedRun;
  return trend.length > 0 ? trend[0].runId : null;
}

export function historyRoute(params, props) {
  const trend = props.dashboardData.dashboard?.trend || [];
  const runs = props.dashboardData.availableRuns || [];
  return (
    <HistoryPage
      trend={trend}
      partialRuns={props.dashboardData.dashboard?.partialRuns || []}
      selection={{
        selectedRunId: resolveHistorySelectedRunId(props.navigation.historySelectedRun, trend),
        selectedRunScore: props.dashboardData.accumulated?.summary?.numericAverage,
      }}
      availableRuns={runs}
      callbacks={{
        onRunClick: (runId, dateLabel) => props.navigation.handleNavigate(NAV_TAB.HISTORY_RUN, { runId, dateLabel }),
        onDimensionClick: (dim) => props.navigation.handleNavigate(NAV_TAB.EXPLORER, { dimension: dim.dimension, runId: dim.fromRunId, dateLabel: dim.fromDateLabel, fromProject: dim.fromProject }),
        onNavigate: props.navigation.handleNavigate,
        onRunChange: props.navigation.setHistorySelectedRun,
        // Drops the run from every cached run list at once, resets a
        // selection that pointed at it, then the same debounced rollup
        // reconcile dismiss/restore use, plus a projects reload.
        onRunDeleted: props.handleRunDeleted,
      }}
      projects={props.navigation.projects}
      projectsLoaded={props.navigation.projectsLoaded}
      selectedProject={props.navigation.selectedProject}
      selectedSource={props.navigation.selectedSource}
      loading={props.dashboardData.loading}
      isFetching={props.dashboardData.isFetching}
      error={props.dashboardData.error}
      onRetry={props.dashboardData.onRetry}
      projectInfo={findProject(props.navigation.projects, props.navigation.selectedProject)}
    />
  );
}
