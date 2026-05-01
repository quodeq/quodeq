import { useCallback, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi } from "../../../api/ApiContext.jsx";
import { useProjectScores } from "../../../hooks/useProjectScores.js";
import { projectKeys } from "../../../api/queryKeys.js";

export function useDashboard({ selectedProject, selectedRun }) {
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
    placeholderData: (prev) => prev,
  });

  const {
    scores,
    latestScores,
    loading: scoresLoading,
    error: scoresError,
    availableRuns,
  } = useProjectScores({ selectedProject, selectedRun });

  const dashboardWithTrend = useMemo(() => {
    if (!dashboardQuery.data) return null;
    const trend = scores?.trend || latestScores?.trend || dashboardQuery.data.trend || [];
    return { ...dashboardQuery.data, trend };
  }, [dashboardQuery.data, scores, latestScores]);

  const refreshDashboard = useCallback(() => {
    if (!selectedProject) return;
    queryClient.invalidateQueries({ queryKey: projectKeys.project(selectedProject) });
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
  };
}
