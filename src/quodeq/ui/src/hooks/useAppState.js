import { useState, useMemo, useEffect, useRef } from 'react';
import { useDashboard } from '../features/dashboard/hooks/useDashboard.js';
import { usePrefetchAdjacentRuns } from '../features/dashboard/hooks/usePrefetchAdjacentRuns.js';
import { buildDailyRuns } from '../utils/dailyGrouping.js';
import { useServerHealth } from './useServerHealth.js';
import { useNavStack } from './useNavStack.js';
import { useRunNavigator } from './useRunNavigator.js';
import { useProjectState } from './useProjectState.js';
import { useAppSettings } from './useAppSettings.js';
import { useEvaluationLifecycle } from './useEvaluationLifecycle.js';
import { useProjectActions } from './useProjectActions.js';
import { useVisibleRuns } from './useVisibleRuns.js';

export const TAB_OVERVIEW = 'overview';
const TAB_HISTORY_RUN = 'history-run';
export const KNOWN_TABS = [TAB_OVERVIEW, 'violations', 'map', 'history', 'projects', 'evaluate', 'standards', 'help', 'settings'];
export const PROJECT_TABS = KNOWN_TABS.slice(0, 4);

function computeDerivedState(accumulated, dashboard, selectedProject, projects) {
  const accDims = accumulated?.dimensions || [];
  let headerMeta = null;
  if (accDims.length > 0) {
    let discipline = null, repository = null;
    for (const d of accDims) {
      if (!discipline && d.discipline) discipline = d.discipline;
      if (!repository && d.repository) repository = d.repository;
      if (discipline && repository) break;
    }
    const runDims = dashboard?.dimensions || [];
    let totalFiles = null;
    for (const d of runDims) {
      if (d.sourceFileCount) { totalFiles = d.sourceFileCount; break; }
    }
    const projectMap = new Map(projects.map((p) => [p.id, p]));
    const project = projectMap.get(selectedProject);
    const languageStats = project?.languageStats ?? null;
    headerMeta = { discipline, repository, totalFiles, languageStats };
  }

  let selectedDisplayName = selectedProject;
  let selectedProjectParent = null;
  let selectedProjectParentId = null;
  if (selectedProject && projects.length) {
    const projectById = new Map(projects.map((p) => [(p.id || p.name || p), p]));
    const data = projectById.get(selectedProject);
    const parentRef = data?.parent || null;
    const parentData = parentRef ? projectById.get(parentRef) : null;
    selectedDisplayName = data?.displayName || data?.name || selectedProject;
    selectedProjectParent = parentData?.displayName || parentData?.name || parentRef;
    selectedProjectParentId = parentData ? (parentData.id || parentData.name || parentRef) : null;
  }

  return { headerMeta, selectedDisplayName, selectedProjectParent, selectedProjectParentId };
}

function useProjects() {
  const projectState = useProjectState();
  const projectActions = useProjectActions({
    projects: projectState.projects,
    selectedProject: projectState.selectedProject,
    handleProjectChange: projectState.handleProjectChange,
    loadProjects: projectState.loadProjects,
  });
  return { ...projectState, ...projectActions };
}

function useAppNavigation() {
  const [serverConnected, setServerConnected, serverVersion] = useServerHealth();
  const { navStack, activePage, navPush, navPop, navGoTo, navReset, navTab } = useNavStack();
  const projectBundle = useProjects();
  const { selectedRun, setSelectedRun, handleRunChange } = projectBundle;
  const [historySelectedRun, setHistorySelectedRun] = useState('latest');
  function handleNavigate(page, params = {}) {
    if (page === 'run' && params.runId) setSelectedRun(params.runId);
    if (page === 'history-run' && params.runId) setHistorySelectedRun(params.runId);
    navPush({ page, ...params });
  }
  return { serverConnected, setServerConnected, serverVersion, navStack, activePage, navPush, navPop, navGoTo, navReset, navTab, projectBundle, handleNavigate, handleRunChange, historySelectedRun, setHistorySelectedRun };
}

export function formatDayLabel(trend, currentOverviewRun, dailyRuns, overviewRunIndex) {
  const entry = (trend || []).find((r) => r.runId === currentOverviewRun);
  if (entry?.dateISO) {
    try {
      return new Date(entry.dateISO).toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' });
    } catch { return entry.dateISO; }
  }
  return dailyRuns[overviewRunIndex]?.dateLabel || currentOverviewRun;
}

export function useAppState() {
  const nav = useAppNavigation();
  const { serverConnected, setServerConnected, serverVersion, navStack, activePage, navPop, navGoTo, navReset, navTab, projectBundle, handleNavigate, handleRunChange, historySelectedRun, setHistorySelectedRun } = nav;
  const {
    projects, projectsLoaded, setProjects, selectedProject,
    selectedRun, setSelectedRun, loadProjects, handleProjectChange,
    selectProjectAndRun, handleDeleteProject, handleExportProject, handleRelocateProject,
  } = projectBundle;
  const settings = useAppSettings();
  const isHistoryRun = activePage.page === 'history-run';
  const isHistoryTab = activePage.page === 'history';
  const effectiveRun = isHistoryRun ? historySelectedRun : selectedRun;
  // History views (the History tab and its run-detail page) show specific
  // past runs in a comparison-oriented mental model — flashing the previous
  // run's data via placeholderData is confusing. Overview navigation, by
  // contrast, benefits from the instant swap because consecutive runs are
  // usually nearly identical.
  const { dashboard, accumulated, latestAccumulated, rescoreLookup, loading, isFetching, error, availableRuns, refreshDashboard } = useDashboard({
    selectedProject,
    selectedRun: effectiveRun,
    keepPlaceholder: !isHistoryRun && !isHistoryTab,
  });
  const { dailyRuns: rawDailyRuns, headerMeta, selectedDisplayName, selectedProjectParent, selectedProjectParentId } = useMemo(() => ({
    dailyRuns: buildDailyRuns(availableRuns, dashboard?.trend || []),
    ...computeDerivedState(accumulated, dashboard, selectedProject, projects),
  }), [availableRuns, dashboard, accumulated, selectedProject, projects]);
  const visibleDailyRuns = useVisibleRuns(rawDailyRuns, dashboard, activePage.page, setSelectedRun);
  const { overviewRunIndex, currentOverviewRun, handleRunPrev, handleRunNext, handleRunLatest, handleRunView, handleRunSelect } = useRunNavigator({ selectedRun, availableRuns: visibleDailyRuns, onRunChange: handleRunChange, onNavigate: handleNavigate });
  const prefetchHandlers = usePrefetchAdjacentRuns({ selectedProject, availableRuns: visibleDailyRuns, overviewRunIndex });
  const evalLifecycle = useEvaluationLifecycle({ settings, navigation: { navTab, navReset }, projects: { loadProjects, setProjects, selectProjectAndRun } });

  // Refresh all dashboard data (including latestAccumulated) when an evaluation finishes
  const evalRefreshedRef = useRef(null);
  useEffect(() => {
    const job = evalLifecycle.job;
    const finished = job && job.status !== 'running' && job.outputRunId;
    if (finished && evalRefreshedRef.current !== job.outputRunId) {
      evalRefreshedRef.current = job.outputRunId;
      refreshDashboard();
    }
  }, [evalLifecycle.job, refreshDashboard]);

  const activeTab = KNOWN_TABS.includes(activePage.page) ? activePage.page
    : activePage.sourceTab && KNOWN_TABS.includes(activePage.sourceTab) ? activePage.sourceTab
    : activePage.page === TAB_HISTORY_RUN ? 'history'
    : TAB_OVERVIEW;
  const showProjectHeader = PROJECT_TABS.includes(activeTab) && projects.length > 0 && !!selectedProject;
  const showRunNav = activeTab === TAB_OVERVIEW && showProjectHeader && visibleDailyRuns.length > 0 && navStack.length === 1;

  return {
    serverConnected, setServerConnected, serverVersion, navStack, activePage, navPop, navGoTo, navTab,
    projects, projectsLoaded, selectedProject, selectedRun, handleProjectChange, handleNavigate,
    handleDeleteProject, handleExportProject, handleRelocateProject,
    dashboard, accumulated, latestAccumulated, rescoreLookup, loading, isFetching, error, availableRuns, dailyRuns: visibleDailyRuns, overviewRunIndex,
    currentOverviewRun, handleRunPrev, handleRunNext, handleRunLatest, handleRunView, handleRunSelect, prefetchHandlers,
    headerMeta, selectedDisplayName, selectedProjectParent, selectedProjectParentId,
    historySelectedRun, setHistorySelectedRun,
    evalLifecycle, settings, activeTab, showProjectHeader, showRunNav, refreshDashboard,
  };
}
