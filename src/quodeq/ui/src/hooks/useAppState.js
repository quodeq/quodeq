import { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import { LOCALE, t } from '../strings/index.js';
import { useQueryClient } from '@tanstack/react-query';
import { useSidePane } from '../features/side-pane/SidePaneContext.jsx';
import { useDashboard } from '../features/dashboard/hooks/useDashboard.js';
import { usePrefetchAdjacentRuns } from '../features/dashboard/hooks/usePrefetchAdjacentRuns.js';
import { buildPeriodRuns } from '../utils/dailyGrouping.js';
import { readScoreHistoryGranularity, writeScoreHistoryGranularity } from '../utils/scoreHistoryPrefs.js';
import { projectKeys } from '../api/queryKeys.js';
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
// 'compare' is appended AFTER the first four on purpose: PROJECT_TABS is a
// positional slice of the head of this list.
export const KNOWN_TABS = [TAB_OVERVIEW, 'violations', 'map', 'history', 'projects', 'evaluate', 'standards', 'help', 'settings', 'compare'];
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

function useProjects({ onNoProjects }) {
  const projectState = useProjectState({ onNoProjects });
  const { showToast } = useSidePane();
  const projectActions = useProjectActions(
    {
      projects: projectState.projects,
      selectedProject: projectState.selectedProject,
      handleProjectChange: projectState.handleProjectChange,
      loadProjects: projectState.loadProjects,
    },
    // Route project-action failures through the toast (SidePaneProvider
    // precedent, e.g. EvaluationForm's onValidationFail) instead of a
    // blocking alert() -- render the message here so useProjectActions
    // stays presentation-agnostic.
    { onError: (messageKey, vars) => showToast(t(messageKey, vars)) },
  );
  return { ...projectState, ...projectActions };
}

function useAppNavigation() {
  const [serverConnected, setServerConnected, serverVersion] = useServerHealth();
  const { navStack, activePage, navPending, navPush, navPop, navReplace, navGoTo, navSwapAt, navReset, navTab } = useNavStack();
  const projectBundle = useProjects({ onNoProjects: () => { /* wizard handles fresh-user UX in App.jsx */ } });
  // Re-arm a failed projects load when connectivity returns. Without this the
  // manual Retry button is the only way out of the startup failure state after
  // the backend comes back (the health poll recovers on its own; the projects
  // load, a one-shot effect, does not).
  const prevConnectedRef = useRef(serverConnected);
  useEffect(() => {
    const wasConnected = prevConnectedRef.current;
    prevConnectedRef.current = serverConnected;
    if (serverConnected && !wasConnected && projectBundle.projectsLoadFailed) {
      projectBundle.retryLoadProjects();
    }
  }, [serverConnected]); // eslint-disable-line react-hooks/exhaustive-deps
  const { selectedRun, setSelectedRun, handleRunChange } = projectBundle;
  const [historySelectedRun, setHistorySelectedRun] = useState('latest');
  function handleNavigate(page, params = {}) {
    if (page === 'run' && params.runId) setSelectedRun(params.runId);
    if (page === 'history-run' && params.runId) setHistorySelectedRun(params.runId);
    navPush({ page, ...params });
  }
  function handleNavigateReplace(page, params = {}) {
    // In-place variant for view-state changes on the SAME screen (e.g. the
    // repositories local/online tabs): history must not grow per flip.
    navReplace({ page, ...params });
  }
  return { serverConnected, setServerConnected, serverVersion, navStack, activePage, navPending, navPush, navPop, navGoTo, navSwapAt, navReset, navTab, projectBundle, handleNavigate, handleNavigateReplace, handleRunChange, historySelectedRun, setHistorySelectedRun };
}

export function formatDayLabel(trend, currentOverviewRun, dailyRuns, overviewRunIndex) {
  const entry = (trend || []).find((r) => r.runId === currentOverviewRun);
  if (entry?.dateISO) {
    try {
      return new Date(entry.dateISO).toLocaleDateString(LOCALE, { day: 'numeric', month: 'long', year: 'numeric' });
    } catch { return entry.dateISO; }
  }
  return dailyRuns[overviewRunIndex]?.dateLabel || currentOverviewRun;
}

// Returning to the Overview from another tab must reconcile any project query
// a mark-stale-only invalidation left behind (refreshDashboard's
// refetchType:'none', or ordinary staleTime elapse): the Overview's
// useDashboard observer is mounted at the app root and never remounts on tab
// navigation, and the desktop pywebview window never fires the focus-refetch
// a browser tab gets on refocus. `stale: true` keeps this a no-op when
// nothing is actually stale, so switching tabs doesn't re-download the
// (potentially 10-20 MB) payload on every visit — only a query already
// marked stale gets refetched here.
//
// Gates on `rootTab` (navStack[0].page), NOT the derived `activeTab`.
// `activeTab`'s fallback bucket defaults any untagged/unknown page to
// TAB_OVERVIEW -- and drill-down pages pushed without a `sourceTab` (e.g.
// ExplorerPage's onPrincipleClick -> 'evalprinciple', handleCardNavigate ->
// 'file') hit that fallback while the user is still mid-triage inside
// Violations/Map. That would misfire a real refetch of the (potentially
// 10-20 MB) payload during triage -- exactly the freeze this stack exists to
// avoid. `navTab()` (useNavStack.js) always resets the stack to a single root
// entry and `navPush` only appends, so `navStack[0].page` is the true
// top-level tab regardless of drill-down depth or sourceTab tagging.
// Exported (and taking plain values rather than reading nav state itself) so
// the transition-gating logic is testable without mounting all of useAppState.
export function useOverviewReturnReconcile({ rootTab, selectedProject, selectedSource }) {
  const queryClient = useQueryClient();
  const prevTabRef = useRef(rootTab);
  useEffect(() => {
    const cameToOverview = prevTabRef.current !== TAB_OVERVIEW && rootTab === TAB_OVERVIEW;
    prevTabRef.current = rootTab;
    if (!cameToOverview || !selectedProject) return;
    queryClient.refetchQueries({
      queryKey: projectKeys.project(selectedProject, selectedSource),
      stale: true,
      type: 'active',
    });
  }, [rootTab, selectedProject, selectedSource, queryClient]);
}

/**
 * The sidebar's active-tab fallback rule: a known top-level page passes
 * through, a drill-down page tagged with `sourceTab` falls back to that tab
 * when it is itself a known tab, `history-run` buckets under `history`, and
 * everything else defaults to Overview.
 *
 * Caveat: a drill-down page pushed WITHOUT a `sourceTab` (e.g. ExplorerPage's
 * onPrincipleClick -> 'evalprinciple', handleCardNavigate -> 'file') hits the
 * Overview fallback here even while the user is still mid-triage inside
 * Violations/Map. That is WHY useOverviewReturnReconcile above gates its
 * refetch on `rootTab` (navStack[0].page) instead of this derived value —
 * see its comment.
 */
export function resolveActiveTab(activePage) {
  if (KNOWN_TABS.includes(activePage.page)) return activePage.page;
  if (activePage.sourceTab && KNOWN_TABS.includes(activePage.sourceTab)) return activePage.sourceTab;
  if (activePage.page === TAB_HISTORY_RUN) return 'history';
  return TAB_OVERVIEW;
}

export function useAppState() {
  const nav = useAppNavigation();
  const { serverConnected, setServerConnected, serverVersion, navStack, activePage, navPending, navPop, navGoTo, navSwapAt, navReset, navTab, projectBundle, handleNavigate, handleNavigateReplace, handleRunChange, historySelectedRun, setHistorySelectedRun } = nav;
  const {
    projects, projectsLoaded, projectsLoadFailed, retryLoadProjects, setProjects, selectedProject, selectedSource,
    selectedRun, setSelectedRun, loadProjects, handleProjectChange,
    selectProjectAndRun, handleDeleteProject, handleExportProject, handleRelocateProject, handleImportProject,
    warmup,
  } = projectBundle;
  const settings = useAppSettings();
  const [granularity, setGranularity] = useState(() => readScoreHistoryGranularity());
  const handleGranularityChange = useCallback((next) => {
    setGranularity(next);
    writeScoreHistoryGranularity(next);
  }, []);
  const isHistoryRun = activePage.page === 'history-run';
  const isHistoryTab = activePage.page === 'history';
  const effectiveRun = isHistoryRun ? historySelectedRun : selectedRun;
  // History views (the History tab and its run-detail page) show specific
  // past runs in a comparison-oriented mental model — flashing the previous
  // run's data via placeholderData is confusing. Overview navigation, by
  // contrast, benefits from the instant swap because consecutive runs are
  // usually nearly identical. The dashboard-refreshing class dims the
  // page during the background refetch so the user sees that something
  // is happening without the jarring full-screen LoadingScreen.
  const { dashboard, accumulated, latestAccumulated, rescoreLookup, loading, isFetching, scoresPending, error, availableRuns, refreshDashboard, refreshDashboardActive, scheduleDashboardReconcile, sharedProjectInfo } = useDashboard({
    selectedProject,
    selectedRun: effectiveRun,
    selectedSource,
    keepPlaceholder: !isHistoryRun && !isHistoryTab,
  });
  const { dailyRuns: rawDailyRuns, headerMeta, selectedDisplayName, selectedProjectParent, selectedProjectParentId } = useMemo(() => ({
    dailyRuns: buildPeriodRuns(availableRuns, dashboard?.trend || [], granularity),
    ...computeDerivedState(accumulated, dashboard, selectedProject, projects),
  }), [availableRuns, dashboard, accumulated, selectedProject, projects, granularity]);
  const visibleDailyRuns = useVisibleRuns(rawDailyRuns, dashboard, activePage.page, setSelectedRun, granularity);
  const { overviewRunIndex, currentOverviewRun, handleRunPrev, handleRunNext, handleRunLatest, handleRunView, handleRunSelect } = useRunNavigator({ selectedRun, availableRuns: visibleDailyRuns, onRunChange: handleRunChange, onNavigate: handleNavigate });
  const prefetchHandlers = usePrefetchAdjacentRuns({ selectedProject, selectedSource, availableRuns: visibleDailyRuns, overviewRunIndex });
  const evalLifecycle = useEvaluationLifecycle({ settings, navigation: { navTab, navReset }, projects: { loadProjects, setProjects, selectProjectAndRun }, selectedProject });

  const activeTab = resolveActiveTab(activePage);
  const showProjectHeader = PROJECT_TABS.includes(activeTab) && projects.length > 0 && !!selectedProject;
  const showRunNav = activeTab === TAB_OVERVIEW && showProjectHeader && visibleDailyRuns.length > 0 && navStack.length === 1;

  useOverviewReturnReconcile({ rootTab: navStack[0]?.page, selectedProject, selectedSource });

  return {
    serverConnected, setServerConnected, serverVersion, navStack, activePage, navPending, navPop, navGoTo, navSwapAt, navTab,
    projects, projectsLoaded, projectsLoadFailed, retryLoadProjects, warmup, selectedProject, selectedSource, selectedRun, loadProjects, handleProjectChange, handleNavigate, handleNavigateReplace,
    handleDeleteProject, handleExportProject, handleRelocateProject, handleImportProject,
    dashboard, accumulated, latestAccumulated, rescoreLookup, loading, isFetching, scoresPending, error, availableRuns, dailyRuns: visibleDailyRuns, overviewRunIndex, sharedProjectInfo,
    currentOverviewRun, handleRunPrev, handleRunNext, handleRunLatest, handleRunView, handleRunSelect, prefetchHandlers,
    headerMeta, selectedDisplayName, selectedProjectParent, selectedProjectParentId,
    historySelectedRun, setHistorySelectedRun,
    evalLifecycle, settings, activeTab, showProjectHeader, showRunNav, refreshDashboard, refreshDashboardActive, scheduleDashboardReconcile,
    granularity, onGranularityChange: handleGranularityChange,
  };
}
