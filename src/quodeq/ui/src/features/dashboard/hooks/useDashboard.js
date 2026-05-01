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
    error: dashboardQuery.isError
      ? "Failed to load dashboard data. Check your connection and try refreshing."
      : (scoresError || null),
    availableRuns,
    refreshDashboard,
  };
}
