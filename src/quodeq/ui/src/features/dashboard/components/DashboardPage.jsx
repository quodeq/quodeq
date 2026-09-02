import { useEffect, useMemo, useRef, useState } from 'react';
import IncompleteSetupCard from './IncompleteSetupCard.jsx';
import OverviewSkeleton from './OverviewSkeleton.jsx';
import LoadingScreen from '../../../components/LoadingScreen.jsx';
import WarmupNotice from '../../../components/WarmupNotice.jsx';
import { t } from '../../../strings/index.js';
import { useDashboardPageState } from '../hooks/useDashboardPageState.js';
import { useDashboardHandlers } from '../hooks/useDashboardHandlers.js';
import { preloadRunHistoryPanel } from './AccumulatedOverviewPanel.jsx';
import DashboardContent from './DashboardContent.jsx';
import {
  ProjectsLoadFailedState, NoLocalProjectsSharedContent, NoProjectsContent, NoProjectSelectedContent,
  LoadingProjectContent, LoadProjectFailedContent, NoRunsEmptyContent, RunLoadFailedContent,
} from './DashboardPageEmptyStates.jsx';

// ---------------------------------------------------------------------------
// DashboardPage — body only, header is rendered by App.jsx
// Top-level page component that receives all dashboard state and callbacks
// directly from App; the high prop count is intentional and not worth splitting.
// The ready-state body (DashboardContent) and the click-handler memo
// (useDashboardHandlers) live in sibling files; the early-return ladder below
// is DOM-identity-pinned (each branch's wrapper element type/position is load
// -bearing for the fade/appear latch -- see useDashboardPageState) and stays
// here whole.
// ---------------------------------------------------------------------------

// Shared projects aren't in the LOCAL projects list, and a shared selection's
// id can collide with an unrelated local project (e.g. after a clone-on-add
// pull) -- looking it up in `projects` would silently bleed the local twin's
// languageStats/publishedBy/etc. into a shared Overview. `sharedProjectInfo`
// is fetched separately (useDashboard, keyed by source) and is exactly this
// shared project's own info. Local behavior is unchanged: same lookup, same
// null fallback. Exported so the source-gating contract is unit-testable
// without mounting the whole page (which needs a SidePaneProvider and more).
export function selectDashboardProjectInfo({ selectedSource, projects, selectedProject, sharedProjectInfo }) {
  const localProjectInfo = (projects || []).find((p) => (p.id || p.name) === selectedProject) || null;
  return selectedSource === 'shared' ? (sharedProjectInfo || null) : localProjectInfo;
}

export default function DashboardPage({ data = {}, callbacks = {}, runMode = false }) {
  const { selectedProject, selectedSource, selectedRun, projects = [], sharedProjectInfo = null, dashboard, accumulated, loading, isFetching, scoresPending = false, error, availableRuns = [], dailyRuns, overviewRunIndex = 0, granularity = 'day', onGranularityChange, sharedHasContent = false, customFormula = false, warmup = null } = data;
  const projectInfo = selectDashboardProjectInfo({ selectedSource, projects, selectedProject, sharedProjectInfo });
  const { onNavigate, onRunSelect, onProjectsReload } = callbacks;
  // Warm the score-history chunk while the boot loader / skeleton is still
  // up: the chart is a separate lazy chunk, and without this the first
  // data-bearing mount commits its placeholder for a beat inside otherwise
  // real content — the exact flash the startup hold exists to remove.
  useEffect(() => { preloadRunHistoryPanel(); }, []);
  // After a successful clone-on-add migration the project's repository_info.json
  // has been rewritten with location: "local". Refetch the projects list so the
  // sidebar/header reflect the new state. Fall back to a full reload if no
  // refetch hook is plumbed through.
  const handleSetupComplete = () => {
    if (typeof onProjectsReload === 'function') onProjectsReload();
    else if (typeof window !== 'undefined') window.location.reload();
  };
  const [focusedDimension, setFocusedDimension] = useState(null);
  const selectedRunId = dashboard?.selectedRun?.runId || selectedRun;
  // Clear focused dimension when the active run changes to avoid showing stale data
  const prevRunRef = useRef(selectedRunId);
  useEffect(() => {
    if (prevRunRef.current !== selectedRunId) {
      prevRunRef.current = selectedRunId;
      setFocusedDimension(null);
    }
  }, [selectedRunId]);
  // Accumulated dimensions are pre-rescored from the server — no client-side merge needed
  const accumulatedDimensions = useMemo(() => accumulated?.dimensions || [], [accumulated]);
  const focusedDimensionData = useMemo(() => focusedDimension ? (dashboard?.dimensions || []).find((d) => d.dimension === focusedDimension) || null : null, [focusedDimension, dashboard]);
  const handlers = useDashboardHandlers(onNavigate, dashboard);

  // These hooks MUST stay above the early returns below — calling them after a
  // conditional return changes the hook count between renders (React error
  // #310, a blank-crash on load). The grace/appear/sticky-latch state machine
  // is extracted into useDashboardPageState (hooks/useDashboardPageState.js);
  // its sub-hooks run in the exact order they did when inline here, so the
  // render-phase state adjustments (grace reset, sticky-latch write) and the
  // StrictMode double-invocation semantics they depend on are unchanged.
  const { contentReady, isLoading, showOverviewSkeleton, dashboardAppearClass, showNoRunsEmpty } = useDashboardPageState({
    runMode, dashboard, accumulated, loading, error, selectedProject, selectedSource, selectedRunId,
  });

  const { projectsLoaded, projectsLoadFailed } = data;
  if (!projectsLoaded) {
    // The startup projects load exhausted its retries: offer a retry instead
    // of an unrecoverable spinner (this early return sits above every other
    // error branch, so without this the page spins forever even after the
    // backend recovered). No hooks in either branch — the hook count across
    // the false -> true flip is pinned by tests.
    if (projectsLoadFailed) {
      return <ProjectsLoadFailedState onRetry={callbacks.onProjectsRetry} />;
    }
    // The app-level FadingLoadingScreen overlay covers this state; render
    // nothing here so the loader lives at one stable spot and can fade out.
    return null;
  }
  if (projects.length === 0 && selectedSource !== 'shared') {
    // Zero local projects. When the connected shared repo has published
    // content, the useful next step is browsing it (read-only until pulled)
    // -- not necessarily scanning something locally. Both CTAs land on the
    // repositories tab; the copy is what differs.
    if (sharedHasContent) {
      return (
        <>
          {null}
          <div className={`dashboard-page dashboard-fade dashboard-ready${dashboardAppearClass}`}>
            <NoLocalProjectsSharedContent onNavigate={onNavigate} />
          </div>
        </>
      );
    }
    return (
      <>
        {null}
        <div className={`dashboard-page dashboard-fade dashboard-ready${dashboardAppearClass}`}>
          <NoProjectsContent onNavigate={onNavigate} />
        </div>
      </>
    );
  }
  if (!selectedProject) {
    return (
      <>
        {null}
        <div className={`dashboard-page dashboard-fade dashboard-ready${dashboardAppearClass}`}>
          <NoProjectSelectedContent onNavigate={onNavigate} />
        </div>
      </>
    );
  }
  const projectName = projectInfo?.displayName || projectInfo?.name || selectedProject;
  if (!loading && !dashboard && error) {
    // A failed fetch also lands here (dashboard === null, queries settled).
    // It must render as an error: claiming "No evaluations yet" on a
    // 404/500/timeout tells the user their existing evaluations are gone.
    // While a retry is in flight (error still set, isFetching true), show
    // the loader instead so clicking Retry visibly does something.
    if (isFetching) {
      return (
        <>
          {null}
          <div className={`dashboard-page dashboard-fade dashboard-ready${dashboardAppearClass}`}>
            <LoadingProjectContent projectName={projectName} />
          </div>
        </>
      );
    }
    return (
      <>
        {null}
        <div className={`dashboard-page dashboard-fade dashboard-ready${dashboardAppearClass}`}>
          <LoadProjectFailedContent error={error} onRetry={callbacks.onRetry} />
        </div>
      </>
    );
  }
  if (showNoRunsEmpty) {
    return (
      <>
        {null}
        <div className={`dashboard-page dashboard-fade dashboard-ready${dashboardAppearClass}${isFetching ? ' dashboard-refreshing' : ''}`}>
          <NoRunsEmptyContent projectInfo={projectInfo} onComplete={handleSetupComplete} projectName={projectName} onNavigate={onNavigate} />
        </div>
      </>
    );
  }
  if (runMode && !loading && !dashboard && !error) {
    // createDashboard passes a falsy raw response through unchanged rather
    // than throwing (models/dashboard.js), so "settled, no error, no
    // dashboard" is a valid non-error outcome, not just a theoretical one --
    // this run's data didn't come back. Without this branch it fell through
    // every other check (all gated on runMode being false, or on dashboard
    // being truthy) to a genuinely blank .dashboard-page.
    if (isFetching) {
      return (
        <>
          {null}
          <div className={`dashboard-page dashboard-fade dashboard-ready${dashboardAppearClass}`}>
            <LoadingProjectContent projectName={projectName} />
          </div>
        </>
      );
    }
    return (
      <>
        {null}
        <div className={`dashboard-page dashboard-fade dashboard-ready${dashboardAppearClass}`}>
          <RunLoadFailedContent onRetry={callbacks.onRetry} />
        </div>
      </>
    );
  }

  // True while a *background* fetch is running but we're already showing
  // data (placeholderData kept the previous run on screen during a switch).
  // The page dims itself slightly so the user sees "still working" without
  // the jarring full-screen LoadingScreen.
  const isRefreshing = isFetching && !!dashboard && !isLoading;
  // showOverviewSkeleton is computed above (beside the appear latch, which
  // needs it too) -- from the user's perspective this covers both loader
  // windows as one continuous OverviewSkeleton, no handoff between them.
  // The `dashboard-loading` 40% dim exists to fade *stale* content sitting
  // under the loader overlay. For the Overview the skeleton IS the content
  // (nothing stale is underneath it), so it never dims -- only a runMode
  // load, which still uses the sibling LoadingScreen below, does.
  const isDimmed = isLoading && runMode;
  return (
    <>
      {/* Sibling to .dashboard-page, not a child of it: that div carries the
          `dashboard-loading` opacity-.4 class for exactly as long as this loader
          is shown, and a loader dimmed by its own "still loading" state renders
          its logo at an unreadable 6% opacity. Names the project being loaded --
          a project switch now clears the old payload (placeholderData is
          project-scoped -- see samePlaceholderScope), so this spinner is what
          the user sees right after picking a project; saying which one makes
          the wait legible instead of looking like the page hung. runMode only
          -- the Overview shows the OverviewSkeleton (inside .dashboard-page,
          see showOverviewSkeleton) instead. */}
      {isLoading && runMode && <LoadingScreen variant="inline" message={projectName ? t('overview.loadingProjectMsg', { name: projectName }) : undefined} />}
      <div className={`dashboard-page dashboard-fade ${isDimmed ? 'dashboard-loading' : `dashboard-ready${dashboardAppearClass}`}${isRefreshing ? ' dashboard-refreshing' : ''}`}>
        <IncompleteSetupCard projectInfo={projectInfo} onComplete={handleSetupComplete} />
        {error && <p className="inline-error">{t('overview.loadFailed')}</p>}
        {showOverviewSkeleton && <WarmupNotice warmup={warmup} />}
        {showOverviewSkeleton && <OverviewSkeleton projectName={projectName} />}
        {/* No runMode equivalent of the Overview's grace-fallback loader: in
            runMode contentReady is `!!dashboard`, so the instant dashboard lands
            contentReady is already true -- there's no window where dashboard is
            in but content isn't ready yet. The `isLoading && runMode`
            LoadingScreen above is the only loader runMode needs. */}
        {dashboard && contentReady && (
          <DashboardContent
            runMode={runMode}
            data={{ dashboard, selectedRunId, accumulated, accumulatedDimensions, availableRuns, dailyRuns, overviewRunIndex, selectedProject, projectInfo, granularity, selectedSource, scoresPending, customFormula }}
            focus={{ dimension: focusedDimension, setDimension: setFocusedDimension, dimensionData: focusedDimensionData }}
            callbacks={{ onRunSelect, onDimensionCardClick: handlers.handleDimensionCardClick, onAccumulatedDimensionClick: handlers.handleAccumulatedDimensionClick, onFileClick: handlers.handleFileClick, onNavigate, onGranularityChange }}
          />
        )}
      </div>
    </>
  );
}
