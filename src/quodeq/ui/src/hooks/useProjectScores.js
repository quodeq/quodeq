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
import { useApi } from "../api/ApiContext.jsx";
import { projectKeys, samePlaceholderScope } from "../api/queryKeys.js";
import { resolveAsOf, deriveAvailableRuns } from './projectScoresDerived.js';
import { t } from '../strings/index.js';

/**
 * @param {{
 *   selectedProject: string,
 *   selectedRun: string,
 *   selectedSource?: 'local'|'shared',
 *   keepPlaceholder?: boolean,
 * }} opts
 *
 * selectedSource (default 'local'): picks the shared-repo mirror fetcher
 * (sharedGetProjectScores) instead of the local one (getProjectScores) when
 * the selected project is a shared-repo project. Also folded into the query
 * keys so switching sources never serves the other source's cached payload.
 *
 * keepPlaceholder (default true): see useDashboard for rationale.
 */
function buildLatestQueryConfig({ projectKey, selectedSource, fetchScores, selectedProject, keepInScope }) {
  return {
    queryKey: projectKeys.scores(projectKey, null, selectedSource),
    queryFn: () => fetchScores(selectedProject),
    enabled: !!selectedProject,
    staleTime: 60_000,
    // Latest scores are project-wide (no per-run swap), so within one project
    // there is nothing to flash — but a project/source switch must still drop
    // to a real loading state rather than showing the old project's grades.
    placeholderData: keepInScope,
  };
}

function buildScoresQueryConfig({ projectKey, asOf, selectedSource, fetchScores, selectedProject, isLatestSelection, latestQuery, keepPlaceholder, keepInScope }) {
  return {
    queryKey: projectKeys.scores(projectKey, asOf, selectedSource),
    queryFn: () => fetchScores(selectedProject, asOf),
    // Wait for the latest run-status list before issuing a scoped fetch —
    // otherwise we'd briefly call with the raw selectedRun and only later
    // correct it, leaking a stale-asOf request.
    enabled: !!selectedProject && (isLatestSelection || latestQuery.isSuccess),
    // A non-null asOf always names a completed run (in-progress falls back
    // to null above), and as-of scores for a completed run only change via
    // explicit actions (dismiss/delete/formula) — all of which invalidate
    // the project subtree and force a refetch regardless of staleTime.
    // Freeze to skip the routine background refetch on re-entry.
    staleTime: asOf ? Infinity : 60_000,
    // Keep prior scores visible while switching runs — see useDashboard for
    // rationale. Scoped to this project+source, so a project switch loads clean.
    placeholderData: keepPlaceholder ? keepInScope : undefined,
  };
}

function buildProjectScoresResult({ scoresQuery, latestQuery, availableRuns, refreshScores }) {
  return {
    scores: scoresQuery.data ?? null,
    latestScores: latestQuery.data ?? null,
    loading: scoresQuery.isLoading || latestQuery.isLoading,
    // True while the panel is rendering the PREVIOUS selection's scores because
    // the newly-picked run is still in flight. placeholderData keeps those old
    // numbers on screen, so without this the dimension cards look settled while
    // showing another day's grades.
    scoresPending: scoresQuery.isPlaceholderData,
    error:
      (scoresQuery.isError || latestQuery.isError)
        ? t('overview.scoresLoadFailed')
        : null,
    availableRuns,
    refreshScores,
  };
}

export function useProjectScores({ selectedProject, selectedRun, selectedSource = "local", keepPlaceholder = true } = {}) {
  const { getProjectScores, sharedGetProjectScores } = useApi();
  const fetchScores = selectedSource === "shared" ? sharedGetProjectScores : getProjectScores;
  const queryClient = useQueryClient();
  const projectKey = selectedProject || "_none_";
  // Reuse the previous payload only within the same project+source subtree —
  // see samePlaceholderScope for why an unguarded (prev) => prev shows the
  // PREVIOUS project's overview after a project switch.
  const keepInScope = useCallback(
    (prev, prevQuery) => (samePlaceholderScope(prevQuery, projectKey, selectedSource) ? prev : undefined),
    [projectKey, selectedSource],
  );

  const latestQuery = useQuery(buildLatestQueryConfig({ projectKey, selectedSource, fetchScores, selectedProject, keepInScope }));

  // Overview is anchored on completed runs. If selectedRun points at an
  // in-progress run (or one that hasn't shown up in availableRuns yet),
  // fall back to 'latest' so the cards keep showing the last finished
  // evaluation instead of going blank mid-flight. Resolution waits for
  // latestQuery so we never fire the scoped query with a stale asOf.
  const isLatestSelection = !selectedRun || selectedRun === "latest";
  const asOf = useMemo(
    () => resolveAsOf({ isLatestSelection, selectedRun, latestQueryData: latestQuery.data }),
    [isLatestSelection, selectedRun, latestQuery.data]
  );

  const scoresQuery = useQuery(buildScoresQueryConfig({ projectKey, asOf, selectedSource, fetchScores, selectedProject, isLatestSelection, latestQuery, keepPlaceholder, keepInScope }));

  const availableRuns = useMemo(
    () => deriveAvailableRuns({ scoresQueryData: scoresQuery.data, latestQueryData: latestQuery.data }),
    [scoresQuery.data, latestQuery.data]
  );

  const refreshScores = useCallback(() => {
    if (!selectedProject) return;
    queryClient.invalidateQueries({ queryKey: projectKeys.project(selectedProject, selectedSource) });
  }, [queryClient, selectedProject, selectedSource]);

  return buildProjectScoresResult({ scoresQuery, latestQuery, availableRuns, refreshScores });
}
