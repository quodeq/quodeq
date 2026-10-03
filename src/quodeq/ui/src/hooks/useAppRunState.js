/**
 * The selected run's slice of the app shell state: the dashboard query for
 * it, the period-bucketed run list the run navigator walks, and the header
 * facts derived from both. Composed by useAppState, in its hook order.
 */
import { useMemo } from 'react';
import { useDashboard } from '../features/dashboard/hooks/useDashboard.js';
import { usePrefetchAdjacentRuns } from '../features/dashboard/hooks/usePrefetchAdjacentRuns.js';
import { buildPeriodRuns } from '../utils/dailyGrouping.js';
import { useRunNavigator } from './useRunNavigator.js';
import { useVisibleRuns } from './useVisibleRuns.js';
import { useHandleRunDeleted } from './runDeletion.js';
import { NAV_TAB } from '../vocab/navTab.js';
import { projectIdOrSelf } from '../utils/projectIdentity.js';

// The accumulated dimensions all carry the same discipline and repository;
// take the first non-empty of each and stop as soon as both are known.
function findDimensionFacets(dims) {
  let discipline = null, repository = null;
  for (const d of dims) {
    if (!discipline && d.discipline) discipline = d.discipline;
    if (!repository && d.repository) repository = d.repository;
    if (discipline && repository) break;
  }
  return { discipline, repository };
}

// Dimensions that did not scan source report no count, so the first one that
// does is the run's file count.
function firstSourceFileCount(dims) {
  for (const d of dims) {
    if (d.sourceFileCount) return d.sourceFileCount;
  }
  return null;
}

function buildHeaderMeta(accumulated, dashboard, selectedProject, projects) {
  const accDims = accumulated?.dimensions || [];
  if (accDims.length === 0) return null;
  const { discipline, repository } = findDimensionFacets(accDims);
  const totalFiles = firstSourceFileCount(dashboard?.dimensions || []);
  const project = new Map(projects.map((p) => [p.id, p])).get(selectedProject);
  return { discipline, repository, totalFiles, languageStats: project?.languageStats ?? null };
}

// Projects are keyed by id, but older entries only have a name, so both are
// tried before falling back to the raw reference.
function projectLabel(entry, fallback) {
  return entry?.displayName || entry?.name || fallback;
}

function resolveSelectedProjectNames(selectedProject, projects) {
  if (!selectedProject || !projects.length) {
    return { selectedDisplayName: selectedProject, selectedProjectParent: null, selectedProjectParentId: null };
  }
  const projectById = new Map(projects.map((p) => [projectIdOrSelf(p), p]));
  const data = projectById.get(selectedProject);
  const parentRef = data?.parent || null;
  const parentData = parentRef ? projectById.get(parentRef) : null;
  return {
    selectedDisplayName: projectLabel(data, selectedProject),
    selectedProjectParent: projectLabel(parentData, parentRef),
    selectedProjectParentId: parentData ? (parentData.id || parentData.name || parentRef) : null,
  };
}

function computeDerivedState(accumulated, dashboard, selectedProject, projects) {
  return {
    headerMeta: buildHeaderMeta(accumulated, dashboard, selectedProject, projects),
    ...resolveSelectedProjectNames(selectedProject, projects),
  };
}

/**
 * The dashboard for the run the active page shows (the History run on the
 * History run page, the Overview run elsewhere) and the run-deleted handler
 * that keeps both selections and the cache consistent.
 */
export function useSelectedRunDashboard({ activePage, projectBundle, historySelectedRun, setHistorySelectedRun }) {
  const { selectedProject, selectedSource, selectedRun, setSelectedRun } = projectBundle;
  const isHistoryRun = activePage.page === NAV_TAB.HISTORY_RUN, isHistoryTab = activePage.page === NAV_TAB.HISTORY;
  // History views (the History tab and its run-detail page) show specific
  // past runs in a comparison-oriented mental model — flashing the previous
  // run's data via placeholderData is confusing. Overview navigation, by
  // contrast, benefits from the instant swap because consecutive runs are
  // usually nearly identical. The top bar sweeps its pending line and each
  // Overview section mutes its text during the background refetch, so the
  // user sees that something is happening without the full LoadingScreen.
  const dashboardState = useDashboard({
    selectedProject,
    selectedRun: isHistoryRun ? historySelectedRun : selectedRun,
    selectedSource,
    keepPlaceholder: !isHistoryRun && !isHistoryTab,
  });
  const { dropRunFromCache, scheduleDashboardReconcile } = dashboardState;
  const handleRunDeleted = useHandleRunDeleted({ dropRunFromCache, setSelectedRun, historySelectedRun, setHistorySelectedRun, scheduleDashboardReconcile });
  return { ...dashboardState, handleRunDeleted };
}

/**
 * The runs bucketed by *granularity* and trimmed to the visible ones, plus
 * the header facts (file count, facets, display names) for the selection.
 */
export function useRunPeriods({ dashboardState, projectBundle, granularity }) {
  const { availableRuns, dashboard, accumulated } = dashboardState;
  const { selectedProject, projects, setSelectedRun } = projectBundle;
  const { dailyRuns: rawDailyRuns, ...derived } = useMemo(() => ({
    dailyRuns: buildPeriodRuns(availableRuns, dashboard?.trend || [], granularity),
    ...computeDerivedState(accumulated, dashboard, selectedProject, projects),
  }), [availableRuns, dashboard, accumulated, selectedProject, projects, granularity]);
  const visibleDailyRuns = useVisibleRuns(rawDailyRuns, dashboard, setSelectedRun, granularity);
  return { visibleDailyRuns, ...derived };
}

/** Prev/next/latest navigation over the visible runs, with neighbour prefetch. */
export function useOverviewRunNavigation({ projectBundle, visibleDailyRuns, onNavigate }) {
  const { selectedProject, selectedSource, selectedRun, handleRunChange } = projectBundle;
  const runNav = useRunNavigator({ selectedRun, availableRuns: visibleDailyRuns, onRunChange: handleRunChange, onNavigate });
  const prefetchHandlers = usePrefetchAdjacentRuns({ selectedProject, selectedSource, availableRuns: visibleDailyRuns, overviewRunIndex: runNav.overviewRunIndex });
  return { ...runNav, prefetchHandlers };
}
