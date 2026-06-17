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

/**
 * @param {{
 *   selectedProject: string,
 *   selectedRun: string,
 *   keepPlaceholder?: boolean,
 * }} opts
 *
 * keepPlaceholder (default true): see useDashboard for rationale.
 */
export function useProjectScores({ selectedProject, selectedRun, keepPlaceholder = true } = {}) {
  const queryClient = useQueryClient();

  const latestQuery = useQuery({
    queryKey: projectKeys.scores(selectedProject || "_none_", null),
    queryFn: () => getProjectScores(selectedProject),
    enabled: !!selectedProject,
    staleTime: 60_000,
    // Latest scores are project-wide (no per-run swap), so prev-data
    // flashing isn't a concern — keep placeholder unconditionally.
    placeholderData: (prev) => prev,
  });

  // Overview is anchored on completed runs. If selectedRun points at an
  // in-progress run (or one that hasn't shown up in availableRuns yet),
  // fall back to 'latest' so the cards keep showing the last finished
  // evaluation instead of going blank mid-flight. Resolution waits for
  // latestQuery so we never fire the scoped query with a stale asOf.
  const isLatestSelection = !selectedRun || selectedRun === "latest";
  const asOf = useMemo(() => {
    if (isLatestSelection) return null;
    const runs = latestQuery.data?.availableRuns;
    if (!runs) return null;
    const match = runs.find((r) => r.runId === selectedRun);
    if (!match) return null;
    if (match.status === "in_progress") return null;
    return selectedRun;
  }, [isLatestSelection, selectedRun, latestQuery.data]);

  const scoresQuery = useQuery({
    queryKey: projectKeys.scores(selectedProject || "_none_", asOf),
    queryFn: () => getProjectScores(selectedProject, asOf),
    // Wait for the latest run-status list before issuing a scoped fetch —
    // otherwise we'd briefly call with the raw selectedRun and only later
    // correct it, leaking a stale-asOf request.
    enabled: !!selectedProject && (isLatestSelection || latestQuery.isSuccess),
    staleTime: 60_000,
    // Keep prior scores visible while switching runs — see useDashboard for rationale.
    placeholderData: keepPlaceholder ? (prev) => prev : undefined,
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
