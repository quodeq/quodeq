import { useCallback, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi } from "../../../api/ApiContext.jsx";
import { useProjectScores } from "../../../hooks/useProjectScores.js";
import { projectKeys, samePlaceholderScope } from "../../../api/queryKeys.js";
import { isFrozenRun } from '../../../models/runRules.js';
import { t } from '../../../strings/index.js';
import { useDashboardInvalidation } from './useDashboardInvalidation.js';

const EMPTY_TREND = [];

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
// Shared projects aren't in the LOCAL projects list DashboardPage otherwise
// reads projectInfo from, and a shared selection's id can collide with an
// unrelated local project (e.g. after a clone-on-add pull) -- looking it up
// there would silently bleed the local twin's languageStats/publishedBy/etc.
// into a shared Overview. Fetch the shared project's own info instead, keyed
// by source so switching sources never serves the other source's cache.
function buildSharedProjectInfoQueryConfig({ projectKey, selectedSource, sharedGetProjectInfo, selectedProject }) {
  return {
    queryKey: projectKeys.info(projectKey, selectedSource),
    queryFn: () => sharedGetProjectInfo(selectedProject),
    enabled: selectedSource === "shared" && !!selectedProject,
  };
}

// A completed historical run is immutable on disk: its payload only changes
// through explicit user actions (dismiss, delete, verify, grade formula,
// run deletion), and every one of those invalidates the project query
// subtree — which forces a refetch regardless of staleTime. Freezing the
// query here removes the routine time-based background refetch (and the
// dashboard-refreshing dim flash) on re-entering a run view. The rule
// itself (including why an unknown run counts as frozen) lives in
// models/runRules.js.
function buildDashboardQueryConfig({ projectKey, selectedRun, selectedSource, fetchDashboard, selectedProject, frozenRun, keepPlaceholder, keepInScope }) {
  return {
    queryKey: projectKeys.dashboard(projectKey, selectedRun, selectedSource),
    queryFn: () => fetchDashboard(selectedProject, selectedRun),
    enabled: !!selectedProject,
    staleTime: frozenRun ? Infinity : 60_000,
    // Keep showing the previous run's data while a new run loads — instant
    // perceived navigation. isFetching toggles true during the background
    // fetch, which the page reads to show a subtle indicator.
    // Disabled when keepPlaceholder=false (History run details).
    // Scoped to this project+source: a PROJECT switch must fall through to a
    // real loading state instead of parking the old project's overview on
    // screen (see samePlaceholderScope).
    placeholderData: keepPlaceholder ? keepInScope : undefined,
  };
}

function buildDashboardResult({
  dashboardWithTrend, scores, latestScores, dashboardQuery, scoresLoading, scoresPending, scoresError,
  availableRuns, refreshDashboard, refreshDashboardActive, scheduleDashboardReconcile, sharedProjectInfoQuery,
}) {
  return {
    dashboard: dashboardWithTrend,
    accumulated: scores?.accumulated || null,
    latestAccumulated: latestScores?.accumulated || null,
    // How the grade was produced, not what it is. A tuned formula moves every
    // score at once with no other trace, so the Overview has to be able to say
    // so next to the number. This return is an explicit whitelist -- dropping
    // the key here silently removes the warning.
    customFormula: Boolean(scores?.scoring?.customFormula),
    rescoreLookup: {},
    loading: dashboardQuery.isLoading || scoresLoading,
    // True during background refetch when we already have placeholder data
    // (e.g. user switched to a different run). Page shows a subtle
    // shimmer/dim instead of the full loading screen.
    isFetching: dashboardQuery.isFetching,
    // Scores for the newly-picked run are still loading; the panels below are
    // showing the previous selection's numbers until they land.
    scoresPending,
    error: dashboardQuery.isError
      ? t('overview.dashboardLoadFailed')
      : (scoresError || null),
    availableRuns,
    refreshDashboard,
    refreshDashboardActive,
    scheduleDashboardReconcile,
    sharedProjectInfo: sharedProjectInfoQuery.data || null,
  };
}

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
// Trend to use for payloads that lack their own (older cached payloads /
// the grade-formula early-return path). Memoized on its own (by the caller):
// scores and latestScores get new object identities on every
// refetch/resolution even when the trend array they carry hasn't changed,
// and dashboardWithTrend needs a stable reference here to avoid busting its
// own memo. EMPTY_TREND is a module-level constant so the `|| []` default
// doesn't itself mint a fresh identity every render.
function computeFallbackTrend(scores, latestScores) {
  return scores?.trend || latestScores?.trend || EMPTY_TREND;
}

function mergeTrendIntoDashboard(dashboardData, fallbackTrend) {
  if (!dashboardData) return null;
  if (dashboardData.trend?.length) return dashboardData;
  return { ...dashboardData, trend: fallbackTrend };
}

export function useDashboard({ selectedProject, selectedRun, selectedSource = "local", keepPlaceholder = true } = {}) {
  const { getDashboard, sharedGetDashboard, sharedGetProjectInfo } = useApi();
  const fetchDashboard = selectedSource === "shared" ? sharedGetDashboard : getDashboard;
  const queryClient = useQueryClient();
  const projectKey = selectedProject || "_none_";
  const keepInScope = useCallback(
    (prev, prevQuery) => (samePlaceholderScope(prevQuery, projectKey, selectedSource) ? prev : undefined),
    [projectKey, selectedSource],
  );

  const sharedProjectInfoQuery = useQuery(buildSharedProjectInfoQueryConfig({ projectKey, selectedSource, sharedGetProjectInfo, selectedProject }));

  const {
    scores,
    latestScores,
    loading: scoresLoading,
    error: scoresError,
    scoresPending,
    availableRuns,
  } = useProjectScores({ selectedProject, selectedRun, selectedSource, keepPlaceholder });

  const frozenRun = isFrozenRun(selectedRun, availableRuns);

  const dashboardQuery = useQuery(buildDashboardQueryConfig({ projectKey, selectedRun, selectedSource, fetchDashboard, selectedProject, frozenRun, keepPlaceholder, keepInScope }));

  const fallbackTrend = useMemo(() => computeFallbackTrend(scores, latestScores), [scores, latestScores]);

  const dashboardWithTrend = useMemo(
    () => mergeTrendIntoDashboard(dashboardQuery.data, fallbackTrend),
    [dashboardQuery.data, fallbackTrend],
  );

  const { refreshDashboard, refreshDashboardActive, scheduleDashboardReconcile } = useDashboardInvalidation({ queryClient, selectedProject, selectedSource });

  return buildDashboardResult({
    dashboardWithTrend, scores, latestScores, dashboardQuery, scoresLoading, scoresPending, scoresError,
    availableRuns, refreshDashboard, refreshDashboardActive, scheduleDashboardReconcile, sharedProjectInfoQuery,
  });
}
