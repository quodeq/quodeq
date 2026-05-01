/**
 * useProjectScores -- single hook for all score data.
 *
 * Two queries: scores at a specific run (when asOf is set), plus latest
 * scores. TanStack Query handles caching, abort, and refresh.
 *
 * To force a refresh after a mutation (dismiss/restore), call:
 *   queryClient.invalidateQueries({ queryKey: projectKeys.project(p) });
 */
import { useCallback, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getProjectScores } from "../api/index.js";
import { projectKeys } from "../api/queryKeys.js";

export function useProjectScores({ selectedProject, selectedRun }) {
  const queryClient = useQueryClient();
  const asOf = selectedRun && selectedRun !== "latest" ? selectedRun : null;

  const scoresQuery = useQuery({
    queryKey: projectKeys.scores(selectedProject || "_none_", asOf),
    queryFn: () => getProjectScores(selectedProject, asOf),
    enabled: !!selectedProject,
    staleTime: 60_000,
  });

  const latestQuery = useQuery({
    queryKey: projectKeys.scores(selectedProject || "_none_", null),
    queryFn: () => getProjectScores(selectedProject),
    enabled: !!selectedProject,
    staleTime: 60_000,
  });

  const availableRuns = useMemo(() => {
    const fromPayload =
      scoresQuery.data?.availableRuns || latestQuery.data?.availableRuns;
    if (fromPayload && fromPayload.length > 0) return fromPayload;
    const trend = scoresQuery.data?.trend || latestQuery.data?.trend || [];
    return trend.map((row) => ({
      runId: row.runId,
      dateLabel: row.dateLabel || row.runId,
      status: "complete",
    }));
  }, [scoresQuery.data, latestQuery.data]);

  const refreshScores = useCallback(() => {
    if (!selectedProject) return;
    queryClient.invalidateQueries({ queryKey: projectKeys.project(selectedProject) });
  }, [queryClient, selectedProject]);

  return {
    scores: scoresQuery.data ?? null,
    latestScores: latestQuery.data ?? null,
    loading: scoresQuery.isLoading || latestQuery.isLoading,
    error:
      (scoresQuery.isError || latestQuery.isError)
        ? "Failed to load score data. Check your connection and try refreshing."
        : null,
    availableRuns,
    refreshScores,
  };
}
