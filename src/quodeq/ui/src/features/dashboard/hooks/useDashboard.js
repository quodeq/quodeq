import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi } from "../../../api/ApiContext.jsx";
import { useProjectScores } from "../../../hooks/useProjectScores.js";
import { projectKeys } from "../../../api/queryKeys.js";
import { useGradeStream } from "../../explorer/hooks/useGradeStream.js";

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
 */
export function useDashboard({ selectedProject, selectedRun, keepPlaceholder = true }) {
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

  // The canonical run ID is resolved by the server and echoed in the dashboard
  // payload as selectedRun.runId. Use that for the SSE subscription so "latest"
  // always maps to the correct run.
  const resolvedRunId = dashboardWithTrend?.selectedRun?.runId ?? null;

  // Live grade updates via SSE. useGradeStream is a no-op when
  // VITE_USE_LIVE_GRADES !== 'true' or resolvedRunId is null.
  const gradeStream = useGradeStream({ project: selectedProject, runId: resolvedRunId });

  // Override grade fields on dashboard.dimensions when an SSE payload arrives.
  // Violations lists are preserved — only scores/grades change.
  const [livePatches, setLivePatches] = useState(null);
  useEffect(() => {
    if (!gradeStream.payload) return;
    const patchMap = new Map(
      (gradeStream.payload.dimensions || []).map((d) => [d.dimension, d]),
    );
    setLivePatches(patchMap);
  }, [gradeStream.payload]);

  const liveDashboard = useMemo(() => {
    if (!dashboardWithTrend) return null;
    if (!livePatches) return dashboardWithTrend;
    return {
      ...dashboardWithTrend,
      dimensions: (dashboardWithTrend.dimensions || []).map((dim) => {
        const patch = livePatches.get(dim.dimension);
        if (!patch) return dim;
        // Merge only the grade/score fields; preserve violations, compliance,
        // principles, and all other Dimension properties from the initial fetch.
        return {
          ...dim,
          overallScore: patch.overallScore ?? dim.overallScore,
          overallGrade: patch.overallGrade ?? dim.overallGrade,
        };
      }),
    };
  }, [dashboardWithTrend, livePatches]);

  const refreshDashboard = useCallback(() => {
    if (!selectedProject) return;
    queryClient.invalidateQueries({ queryKey: projectKeys.project(selectedProject) });
  }, [queryClient, selectedProject]);

  return {
    dashboard: liveDashboard,
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
