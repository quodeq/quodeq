import { useState, useMemo, useEffect, useRef } from 'react';
import { useDashboard } from '../features/dashboard/hooks/useDashboard.js';
import { buildDailyRuns } from '../utils/dailyGrouping.js';
import { useServerHealth } from './useServerHealth.js';
import { useNavStack } from './useNavStack.js';
import { useRunNavigator } from './useRunNavigator.js';
import { useProjectState } from './useProjectState.js';
import { useAppSettings } from './useAppSettings.js';
import { useEvaluationLifecycle } from './useEvaluationLifecycle.js';
import { useProjectActions } from './useProjectActions.js';
import { useVisibleRuns } from './useVisibleRuns.js';

export const KNOWN_TABS = ['overview', 'violations', 'map', 'history', 'projects', 'evaluate', 'standards', 'settings'];
export const PROJECT_TABS = KNOWN_TABS.slice(0, 4);

function computeDerivedState(accumulated, dashboard, selectedProject, projects) {
  const accDims = accumulated?.dimensions || [];
  let headerMeta = null;
  if (accDims.length > 0) {
    const discipline = accDims.find((d) => d.discipline)?.discipline ?? null;
    const repository = accDims.find((d) => d.repository)?.repository ?? null;
    const runDims = dashboard?.dimensions || [];
    const totalFiles = runDims.find((d) => d.sourceFileCount)?.sourceFileCount ?? null;
    const project = projects.find((p) => p.id === selectedProject);
    const languageStats = project?.languageStats ?? null;
    headerMeta = { discipline, repository, totalFiles, languageStats };
  }

  let selectedDisplayName = selectedProject;
  let selectedProjectParent = null;
  let selectedProjectParentId = null;
  if (selectedProject && projects.length) {
    const data = projects.find((p) => (p.id || p.name || p) === selectedProject);
    const parentRef = data?.parent || null;
    const parentData = parentRef ? projects.find((p) => (p.id || p.name || p) === parentRef) : null;
    selectedDisplayName = data?.displayName || data?.name || selectedProject;
    selectedProjectParent = parentData?.displayName || parentData?.name || parentRef;
    selectedProjectParentId = parentData ? (parentData.id || parentData.name || parentRef) : null;
  }

  return { headerMeta, selectedDisplayName, selectedProjectParent, selectedProjectParentId };
}

function useProjects({ onNoProjects }) {
  const projectState = useProjectState({ onNoProjects });
  const projectActions = useProjectActions({
    projects: projectState.projects,
    selectedProject: projectState.selectedProject,
    handleProjectChange: projectState.handleProjectChange,
    loadProjects: projectState.loadProjects,
  });
  return { ...projectState, ...projectActions };
}

function useAppNavigation() {
  const [serverConnected, setServerConnected] = useServerHealth();
  const { navStack, activePage, navPush, navPop, navGoTo, navReset, navTab } = useNavStack();
  const projectBundle = useProjects({ onNoProjects: () => navTab('evaluate') });
  const { selectedRun, setSelectedRun, handleRunChange } = projectBundle;
  const [historySelectedRun, setHistorySelectedRun] = useState('latest');
  function handleNavigate(page, params = {}) {
    if (page === 'run' && params.runId) setSelectedRun(params.runId);
    if (page === 'history-run' && params.runId) setHistorySelectedRun(params.runId);
    navPush({ page, ...params });
  }
  return { serverConnected, setServerConnected, navStack, activePage, navPush, navPop, navGoTo, navReset, navTab, projectBundle, handleNavigate, handleRunChange, historySelectedRun, setHistorySelectedRun };
}

export function formatDayLabel(trend, currentOverviewRun, dailyRuns, overviewRunIndex) {
  const entry = (trend || []).find((r) => r.runId === currentOverviewRun);
  if (entry?.dateISO) {
    try {
      return new Date(entry.dateISO).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
    } catch { return entry.dateISO; }
  }
  return dailyRuns[overviewRunIndex]?.dateLabel || currentOverviewRun;
}

export function useAppState() {
  const nav = useAppNavigation();
  const { serverConnected, setServerConnected, navStack, activePage, navPop, navGoTo, navReset, navTab, projectBundle, handleNavigate, handleRunChange, historySelectedRun, setHistorySelectedRun } = nav;
  const { projects, projectsLoaded, setProjects, selectedProject, selectedRun, setSelectedRun, loadProjects, handleProjectChange, selectProjectAndRun, handleDeleteProject, handleExportProject, handleRelocateProject } = projectBundle;
  const settings = useAppSettings();
  const effectiveRun = activePage.page === 'history-run' ? historySelectedRun : selectedRun;
  const { dashboard, accumulated, latestAccumulated, rescoreLookup, loading, error, availableRuns, refreshDashboard } = useDashboard({ selectedProject, selectedRun: effectiveRun });
  const { dailyRuns: rawDailyRuns, headerMeta, selectedDisplayName, selectedProjectParent, selectedProjectParentId } = useMemo(() => ({
    dailyRuns: buildDailyRuns(availableRuns, dashboard?.trend || []),
    ...computeDerivedState(accumulated, dashboard, selectedProject, projects),
  }), [availableRuns, dashboard, accumulated, selectedProject, projects]);
  const visibleDailyRuns = useVisibleRuns(rawDailyRuns, dashboard, activePage.page, setSelectedRun);
  const { overviewRunIndex, currentOverviewRun, handleRunPrev, handleRunNext, handleRunLatest, handleRunView, handleRunSelect } = useRunNavigator({ selectedRun, availableRuns: visibleDailyRuns, onRunChange: handleRunChange, onNavigate: handleNavigate });
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
    : activePage.page === 'history-run' ? 'history'
    : 'overview';
  const showProjectHeader = PROJECT_TABS.includes(activeTab) && projects.length > 0 && !!selectedProject;
  const showRunNav = activeTab === 'overview' && showProjectHeader && visibleDailyRuns.length > 0 && navStack.length === 1;

  return {
    serverConnected, setServerConnected, navStack, activePage, navPop, navGoTo, navTab,
    projects, projectsLoaded, selectedProject, selectedRun, handleProjectChange, handleNavigate,
    handleDeleteProject, handleExportProject, handleRelocateProject,
    dashboard, accumulated, latestAccumulated, rescoreLookup, loading, error, availableRuns, dailyRuns: visibleDailyRuns, overviewRunIndex,
    currentOverviewRun, handleRunPrev, handleRunNext, handleRunLatest, handleRunView, handleRunSelect,
    headerMeta, selectedDisplayName, selectedProjectParent, selectedProjectParentId,
    historySelectedRun, setHistorySelectedRun,
    evalLifecycle, settings, activeTab, showProjectHeader, showRunNav, refreshDashboard,
  };
}
