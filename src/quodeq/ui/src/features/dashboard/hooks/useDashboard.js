import { useCallback, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi } from "../../../api/ApiContext.jsx";
import { useProjectScores } from "../../../hooks/useProjectScores.js";
import { projectKeys } from "../../../api/queryKeys.js";

/**
 * @param {{
 *   selectedProject: string,
 *   selectedRun: string,
 *   selectedSource?: 'local'|'shared',
 *   keepPlaceholder?: boolean,
 * }} opts
 *
 * selectedSource (default 'local'): picks the shared-repo mirror fetcher
 * (sharedGetDashboard) instead of the local one (getDashboard) when the
 * selected project is a shared-repo project. Threaded through to
 * useProjectScores and folded into every query key here so switching
 * sources never serves the other source's cached payload.
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
export function useDashboard({ selectedProject, selectedRun, selectedSource = "local", keepPlaceholder = true } = {}) {
  const { getDashboard, sharedGetDashboard, sharedGetProjectInfo } = useApi();
  const fetchDashboard = selectedSource === "shared" ? sharedGetDashboard : getDashboard;
  const queryClient = useQueryClient();

  // Shared projects aren't in the LOCAL projects list DashboardPage otherwise
  // reads projectInfo from, and a shared selection's id can collide with an
  // unrelated local project (e.g. after a clone-on-add pull) -- looking it up
  // there would silently bleed the local twin's languageStats/publishedBy/etc.
  // into a shared Overview. Fetch the shared project's own info instead, keyed
  // by source so switching sources never serves the other source's cache.
  const sharedProjectInfoQuery = useQuery({
    queryKey: projectKeys.info(selectedProject || "_none_", selectedSource),
    queryFn: () => sharedGetProjectInfo(selectedProject),
    enabled: selectedSource === "shared" && !!selectedProject,
  });

  const {
    scores,
    latestScores,
    loading: scoresLoading,
    error: scoresError,
    availableRuns,
  } = useProjectScores({ selectedProject, selectedRun, selectedSource, keepPlaceholder });

  // A completed historical run is immutable on disk: its payload only changes
  // through explicit user actions (dismiss, delete, verify, grade formula,
  // run deletion), and every one of those invalidates the project query
  // subtree — which forces a refetch regardless of staleTime. Freezing the
  // query here removes the routine time-based background refetch (and the
  // dashboard-refreshing dim flash) on re-entering a run view. Unknown
  // status counts as frozen: by the time a run detail is opened the runs
  // list is already cached, and treating the brief unknown window as frozen
  // avoids a spurious mount refetch.
  const runStatus = (availableRuns || []).find((r) => r.runId === selectedRun)?.status;
  const isFrozenRun = !!selectedRun && selectedRun !== "latest" && runStatus !== "in_progress";

  const dashboardQuery = useQuery({
    queryKey: projectKeys.dashboard(selectedProject || "_none_", selectedRun, selectedSource),
    queryFn: () => fetchDashboard(selectedProject, selectedRun),
    enabled: !!selectedProject,
    staleTime: isFrozenRun ? Infinity : 60_000,
    // Keep showing the previous run's data while a new run loads — instant
    // perceived navigation. isFetching toggles true during the background
    // fetch, which the page reads to show a subtle indicator.
    // Disabled when keepPlaceholder=false (History run details).
    placeholderData: keepPlaceholder ? (prev) => prev : undefined,
  });

  const dashboardWithTrend = useMemo(() => {
    if (!dashboardQuery.data) return null;
    // The dashboard payload carries its OWN cache-backed, dismiss-adjusted
    // trend that is byte-identical to scores.trend (tests/services/
    // test_scoring_parity.py pins every read path to the same per-run score).
    // Return the payload UNCHANGED when it has one: the scoped scores query
    // resolves a beat AFTER the dashboard query, and folding scores.trend in
    // then would mint a new `dashboard` object identity. RunOverviewPanel
    // memoizes every derived value on the whole dashboard object and has a fade
    // animation, so a new identity re-renders the panel and replays the fade —
    // the run-detail entry "flicker". Fall back to the scores trend only when
    // the payload lacks one (older cached payloads / the grade-formula
    // early-return path).
    if (dashboardQuery.data.trend?.length) return dashboardQuery.data;
    const trend = scores?.trend || latestScores?.trend || [];
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
      queryKey: projectKeys.project(selectedProject, selectedSource),
      refetchType: 'none',
    });
  }, [queryClient, selectedProject, selectedSource]);

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
      queryKey: projectKeys.project(selectedProject, selectedSource),
    });
  }, [queryClient, selectedProject, selectedSource]);

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
    sharedProjectInfo: sharedProjectInfoQuery.data || null,
  };
}
