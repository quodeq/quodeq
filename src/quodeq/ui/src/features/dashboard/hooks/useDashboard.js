import { useCallback, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi } from "../../../api/ApiContext.jsx";
import { useProjectScores } from "../../../hooks/useProjectScores.js";
import { projectKeys } from "../../../api/queryKeys.js";

/**
 * @param {{
 *   selectedProject: string,
 *   selectedRun: string,
 *   keepPlaceholder?: boolean,
 * }} opts
 *
 * keepPlaceholder (default true): when switching runs, keep the previous
 * run's data on screen during the background fetch. Great for Overview
 * navigation where consecutive runs are similar. Set false in contexts
 * where stale data is misleading (e.g. History run details, where users
 * compare specific runs and the flash of previous data confuses them).
 *
 * Live grade updates after a dismiss arrive via the dismiss HTTP response,
 * not via SSE. ``refreshDashboard`` is what the dismiss handlers call to
 * trigger a refetch of the accumulated (cross-run) dashboard payload.
 */
export function useDashboard({ selectedProject, selectedRun, keepPlaceholder = true } = {}) {
  const { getDashboard } = useApi();
  const queryClient = useQueryClient();

  const dashboardQuery = useQuery({
    queryKey: projectKeys.dashboard(selectedProject || "_none_", selectedRun),
    queryFn: () => getDashboard(selectedProject, selectedRun),
    enabled: !!selectedProject,
    staleTime: 60_000,
    // Keep showing the previous run's data while a new run loads — instant
    // perceived navigation. isFetching toggles true during the background
    // fetch, which the page reads to show a subtle indicator.
    // Disabled when keepPlaceholder=false (History run details).
    placeholderData: keepPlaceholder ? (prev) => prev : undefined,
  });

  const {
    scores,
    latestScores,
    loading: scoresLoading,
    error: scoresError,
    availableRuns,
  } = useProjectScores({ selectedProject, selectedRun, keepPlaceholder });

  const dashboardWithTrend = useMemo(() => {
    if (!dashboardQuery.data) return null;
    const trend = scores?.trend || latestScores?.trend || dashboardQuery.data.trend || [];
    return { ...dashboardQuery.data, trend };
  }, [dashboardQuery.data, scores, latestScores]);

  const refreshDashboard = useCallback(() => {
    if (!selectedProject) return;
    // Mark project queries stale but DON'T trigger an immediate refetch.
    // The dashboard payload is 10-20 MB on large projects (one run's full
    // violation + compliance arrays × multiple dimensions); refetching on
    // every dismiss froze the UI for 1-3 s while the browser parsed the
    // JSON and React re-rendered. The dismiss POST already returned the
    // rescored run for the active page (PrincipleDetail / FileDetail /
    // FindingDetail) to apply locally — the dashboard rollup just needs
    // to be eventually-correct, which React Query handles automatically:
    // ``refetchType: 'none'`` marks the cache stale, the next mount
    // refetches naturally on navigation.
    queryClient.invalidateQueries({
      queryKey: projectKeys.project(selectedProject),
      refetchType: 'none',
    });
  }, [queryClient, selectedProject]);

  // Force-refresh variant for when fresh data is genuinely expected NOW and the
  // user is parked on a mounted observer that won't otherwise refetch — namely
  // when an evaluation finishes. Unlike ``refreshDashboard`` (refetchType:'none',
  // used by the high-frequency dismiss path to avoid re-pulling the 10-20 MB
  // payload), this uses the default refetchType:'active' so the always-mounted
  // Overview observer actually refetches. Without it, a freshly-completed run
  // leaves the Overview showing the stale pre-run payload (empty "No
  // evaluations yet" state) until the user switches projects and back, which is
  // the only other action that re-subscribes the observer to its query key.
  const refreshDashboardActive = useCallback(() => {
    if (!selectedProject) return;
    queryClient.invalidateQueries({
      queryKey: projectKeys.project(selectedProject),
    });
  }, [queryClient, selectedProject]);

  return {
    dashboard: dashboardWithTrend,
    accumulated: scores?.accumulated || null,
    latestAccumulated: latestScores?.accumulated || null,
    rescoreLookup: {},
    loading: dashboardQuery.isLoading || scoresLoading,
    // True during background refetch when we already have placeholder data
    // (e.g. user switched to a different run). Page shows a subtle
    // shimmer/dim instead of the full loading screen.
    isFetching: dashboardQuery.isFetching,
    error: dashboardQuery.isError
      ? "Failed to load dashboard data. Check your connection and try refreshing."
      : (scoresError || null),
    availableRuns,
    refreshDashboard,
    refreshDashboardActive,
  };
}
