import { useEffect, useMemo, useRef, useState } from 'react';
import DimensionCard from './DimensionCard.jsx';
import AccumulatedOverviewPanel, { preloadRunHistoryPanel } from './AccumulatedOverviewPanel.jsx';
import RunOverviewPanel from './RunOverviewPanel.jsx';
import IncompleteSetupCard from './IncompleteSetupCard.jsx';
import OverviewSkeleton from './OverviewSkeleton.jsx';
import LoadingScreen from '../../../components/LoadingScreen.jsx';
import WarmupNotice from '../../../components/WarmupNotice.jsx';
import EmptyState from '../../../components/EmptyState.jsx';
import { t } from '../../../strings/index.js';

// Matches the .dashboard-appear animation length (dashboard.css) -- the
// class is held for this long so re-renders can't cut the fade short.
const DASHBOARD_APPEAR_MS = 400;

function NoCompletedEvalPanel({ availableRuns = [], onNavigate, selectedSource }) {
  const hasRunning = availableRuns.some((r) => r?.status === 'in_progress');
  if (hasRunning) {
    // First-ever evaluation is still running. There's no prior data to
    // show, but we still avoid claiming the project has "no" evaluations
    // — they just haven't finished yet.
    return (
      <EmptyState
        title={t('overview.firstEvalTitle')}
        description={t('overview.firstEvalDesc')}
        actionLabel={t('overview.openHistory')}
        onAction={() => onNavigate?.('history')}
      />
    );
  }
  // Shared projects are read-only in the app -- evaluations only ever run
  // locally (see api/shared.js's read-only-mirrors note), so the "Start
  // evaluation" CTA has nowhere useful to send a shared-project viewer. Show
  // the same empty shell without the button and with copy that doesn't imply
  // there's an action to take here.
  if (selectedSource === 'shared') {
    return (
      <EmptyState
        title={t('overview.noCompletedEvalTitle')}
        description={t('overview.noCompletedEvalSharedDesc')}
      />
    );
  }
  return (
    <EmptyState
      title={t('overview.noCompletedEvalTitle')}
      description={t('overview.noCompletedEvalDesc')}
      actionLabel={t('overview.startEvaluation')}
      onAction={() => onNavigate?.('evaluate')}
    />
  );
}

function DashboardContent({ runMode, data, focus, callbacks }) {
  const { dashboard, selectedRunId, accumulated, accumulatedDimensions, availableRuns, dailyRuns, overviewRunIndex, selectedProject, projectInfo, granularity, selectedSource, scoresPending, customFormula } = data;
  const { dimension: focusedDimension, setDimension: setFocusedDimension, dimensionData: focusedDimensionData } = focus;
  const { onRunSelect, onDimensionCardClick, onAccumulatedDimensionClick, onFileClick, onNavigate, onGranularityChange } = callbacks;
  // No readiness check here on purpose: the page only mounts this component
  // once contentReady is true (see DashboardPage's return), so there is
  // exactly one place in the whole page that decides whether a loader is
  // shown -- never a render decision split between here and the parent.
  if (runMode) {
    return (
      <RunOverviewPanel
        dashboard={dashboard}
        selectedRunId={selectedRunId}
        projectName={projectInfo?.displayName || projectInfo?.name || selectedProject}
        onDimensionClick={onDimensionCardClick}
        onFileClick={onFileClick}
        onNavigate={onNavigate}
      />
    );
  }
  if (accumulatedDimensions.length === 0) {
    // Project has runs (otherwise the upstream `!dashboard` empty
    // state would have fired) but none have terminated cleanly yet —
    // first evaluation in progress, or every prior attempt was
    // cancelled/failed. Render a clear waiting-for-results state in
    // place of the empty stat strip and dim cards (the page header
    // above still shows project name, language mix, file count).
    return <NoCompletedEvalPanel availableRuns={availableRuns} onNavigate={onNavigate} selectedSource={selectedSource} />;
  }
  if (focusedDimension) {
    return (
      <div className="dimensions-panel">
        <div className="section-header">
          <h3 className="section-title">{focusedDimension}</h3>
          <button type="button" className="btn-secondary" onClick={() => setFocusedDimension(null)}>
            {t('overview.showAll')}
          </button>
        </div>
        <DimensionCard title={focusedDimension} dimension={focusedDimensionData} isSingleFocus={true} />
      </div>
    );
  }
  return (
    <AccumulatedOverviewPanel
      data={{
        accumulated: accumulated ? { ...accumulated, dimensions: accumulatedDimensions } : accumulated,
        accumulatedDimensions, availableRuns, dailyRuns, overviewRunIndex,
        trend: dashboard?.trend || [], selectedRunId, selectedProject, projectInfo, granularity, selectedSource,
        scoresPending, customFormula,
      }}
      callbacks={{
        onRunClick: onRunSelect, onDimensionClick: onAccumulatedDimensionClick, onNavigate, onGranularityChange,
      }}
    />
  );
}

// ---------------------------------------------------------------------------
// DashboardPage — body only, header is rendered by App.jsx
// Top-level page component that receives all dashboard state and callbacks
// directly from App; the high prop count is intentional and not worth splitting.
// ---------------------------------------------------------------------------

function useDashboardHandlers(onNavigate, dashboard) {
  return useMemo(() => ({
    handleDimensionCardClick: (item, runId) => {
      if (!onNavigate) return;
      const dateLabel = dashboard?.selectedRun?.dateLabel || item.fromDateLabel;
      onNavigate('explorer', { dimension: item.dimension, runId: runId || item.fromRunId, dateLabel, fromProject: item.fromProject });
    },
    handleAccumulatedDimensionClick: (item) => {
      if (onNavigate) onNavigate('explorer', { dimension: item.dimension, runId: item.fromRunId, dateLabel: item.fromDateLabel, fromProject: item.fromProject });
    },
    handleFileClick: (fileObj) => { if (onNavigate) onNavigate('file', { file: fileObj }); },
  }), [onNavigate, dashboard]);
}

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

  // What each view needs before it can render real content: run detail only
  // needs the dashboard payload; the Overview also needs the scores-derived
  // `accumulated` block. This is the single readiness rule for the whole page
  // -- DashboardContent is only mounted once it holds, and never re-derives
  // its own readiness from `accumulated`, so there is exactly one loader
  // decision instead of two that can disagree.
  // These hooks MUST stay above the early returns below — calling them after a
  // conditional return changes the hook count between renders (React error
  // #310, a blank-crash on load).
  const contentReady = runMode ? !!dashboard : (!!dashboard && !!accumulated);
  // Grace state for the slow/cold-load fallback (consumed by isLoading below).
  const [graceElapsed, setGraceElapsed] = useState(false);
  // Reset synchronously during render, not from the effect below: contentReady
  // flipping true (or dashboard disappearing) and graceElapsed resetting are
  // the same logical transition. Doing it from an effect meant a stale
  // intermediate commit (graceElapsed still true) landed first and ran ITS
  // OWN effects -- including the appear-fade latch's ref write further down
  // -- before this effect got a chance to correct it; a second, cascading
  // commit then found the latch already spent and dropped the fade it had
  // just armed. Resetting here settles the transition in a single commit,
  // before any effects run at all -- same "adjust state during render"
  // pattern as noRunsEmptySticky below, safe under StrictMode's double-
  // render for the same reason: idempotent once the condition clears.
  if (graceElapsed && (contentReady || !dashboard)) setGraceElapsed(false);
  useEffect(() => {
    if (contentReady || !dashboard) return undefined;
    const timer = setTimeout(() => setGraceElapsed(true), 700);
    return () => clearTimeout(timer);
  }, [contentReady, dashboard]);

  // Hold the full LoadingScreen until the content is ready, so we don't fade in
  // a half-drawn page and then pop the real content in a beat later (the
  // first-load flicker). BUT a cold score cache can take several seconds to
  // rebuild (e.g. right after a dismiss/restore/formula change invalidates it);
  // sitting on a blank spinner that whole time reads as "not opening". So once
  // the dashboard payload is in and the grace has elapsed (graceElapsed, set
  // above), fall back to the partial page (frame + a content spinner) so a slow
  // load shows progress instead of a hang. The grace comfortably exceeds a warm
  // load, so the fast path still gets one clean transition.
  // Hoisted above the early returns (rather than kept by the main return where
  // it's consumed) because the fade-once latch below needs it for every branch,
  // not just the main one.
  const isLoading = loading && !contentReady && !(dashboard && graceElapsed);

  // Overview only (!runMode): both loader windows below (isLoading itself,
  // and the grace-fallback window once dashboard has landed but accumulated
  // hasn't) render one continuous OverviewSkeleton instead of a LoadingScreen.
  // Computed here, above the appear latch, rather than beside the return
  // where it's consumed: the latch below needs to know a skeleton (not real
  // content) is what's showing, for every branch, not just the main one --
  // same reason `isLoading` itself is hoisted above the early returns.
  const showOverviewSkeleton = !runMode && !!(isLoading || (dashboard && !isLoading && !contentReady));

  // Fade-once latch: `dashboard-fadein` should play when the page's content
  // first appears for this project/source/run context, not on every
  // loading<->ready flip within it (grace-fallback then content-ready, an
  // error settling, the no-runs sticky state handing off to real content).
  // Keyed like noRunsScopeKey below, but the run is folded in too so a run
  // switch on run-detail gets its own fade. The animation itself lives on a
  // separate `dashboard-appear` class (kept apart from the `dashboard-ready`
  // state class) so re-adding `dashboard-ready` alone -- e.g. dropping
  // `dashboard-refreshing` -- never replays it. The ref is only written from
  // an effect (post-commit), never during render: mutating it inline would
  // make the appear decision depend on how many times React happens to
  // invoke this render (StrictMode double-invokes it in dev).
  // isLoading, reused below as "was this render ready", isn't guaranteed
  // false on every render of every early-return branch -- e.g. the no-runs
  // sticky branch below CAN be reached with isLoading true, once
  // wasNoRunsEmpty is already latched (a repeat render of an already-shown
  // context, gated by showNoRunsEmpty's `!loading || wasNoRunsEmpty` below).
  // What matters is narrower and does hold: on the render where a context's
  // empty/error state genuinely first appears, `loading` is false --
  // showNoRunsEmpty requires `!loading` until wasNoRunsEmpty is latched, and
  // the error/runMode-empty branches gate on `!loading` outright -- so the
  // latch is never consumed before real first-appearance content is on
  // screen; isLoading being true only ever suppresses a repeat.
  // `!showOverviewSkeleton` gates both the read and the write: without it,
  // the grace-elapsed flip (isLoading true -> false while the Overview's
  // skeleton keeps showing, accumulated still pending) would (a) play the
  // 400ms fade over a skeleton that was already fully visible and unchanged
  // -- a flash the skeleton is supposed to avoid -- and (b) spend the latch
  // early, so the *real* content that mounts once accumulated lands would
  // get no fade at all. showOverviewSkeleton is false for every other branch
  // (runMode, error, empty states, sticky no-runs), so this is a no-op there.
  const dashboardAppearKey = `${selectedProject}::${selectedSource}::${runMode ? selectedRunId : 'overview'}`;
  const dashboardAppearedKeyRef = useRef(null);
  const dashboardAppearNow = !isLoading && !showOverviewSkeleton && dashboardAppearedKeyRef.current !== dashboardAppearKey;
  useEffect(() => {
    if (!isLoading && !showOverviewSkeleton) dashboardAppearedKeyRef.current = dashboardAppearKey;
  }, [isLoading, showOverviewSkeleton, dashboardAppearKey]);
  // Hold the class for the animation's duration, not just the one render
  // where dashboardAppearNow computes true: an unrelated re-render inside
  // the window (isFetching flipping a moment after content appeared) used
  // to drop it and snap opacity to 1, cutting the fade short. The className
  // never toggles mid-window, so the animation runs uninterrupted; removal
  // after the window is visually a no-op (the animation has finished).
  // Latching until the key next changes was rejected instead: a key change
  // then re-applies the class onto a node that still has it, which does not
  // restart a CSS animation.
  const [appearHeld, setAppearHeld] = useState(false);
  const appearTimerRef = useRef(null);
  useEffect(() => {
    if (!dashboardAppearNow) return;
    setAppearHeld(true);
    clearTimeout(appearTimerRef.current);
    appearTimerRef.current = setTimeout(() => setAppearHeld(false), DASHBOARD_APPEAR_MS);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dashboardAppearNow, dashboardAppearKey]);
  useEffect(() => () => clearTimeout(appearTimerRef.current), []);
  const dashboardAppearClass = (dashboardAppearNow || appearHeld) ? ' dashboard-appear' : '';

  // Sticky "no evaluations yet" latch: once that empty state is showing for
  // this project+source, stay on it through a subsequent load (the post-eval
  // selectedRun flip -- new dashboard key, loading true, dashboard still
  // null) instead of popping to the full inline loader for a beat. Keyed off
  // project+source so a project switch never inherits the previous
  // project's stickiness (see the reset check below). runMode never shows
  // this empty state, so it's excluded outright -- and a runMode render must
  // never touch the latch at all: App.jsx doesn't always remount DashboardPage
  // between the Overview and a run detail view for the same project+source,
  // so writing `active: false` here on a runMode pass would clear a
  // legitimately-active Overview latch out from under it.
  const noRunsScopeKey = `${selectedProject}::${selectedSource}`;
  const [noRunsEmptySticky, setNoRunsEmptySticky] = useState({ scopeKey: noRunsScopeKey, active: false });
  const wasNoRunsEmpty = noRunsEmptySticky.scopeKey === noRunsScopeKey && noRunsEmptySticky.active;
  // Latch on !contentReady, not !dashboard: releasing the latch the moment
  // the dashboard payload lands (but before accumulated does) reopened the
  // same pop this latch exists to close, just narrower -- empty(dimmed) ->
  // inline spinner -> content instead of loader -> content. contentReady
  // already folds in the accumulated wait for the Overview (runMode is
  // excluded from this branch outright, so its own dashboard-only readiness
  // never applies here), so holding the empty state open until BOTH payloads
  // land closes the gap without a separate flag to keep in sync.
  const showNoRunsEmpty = !runMode && !contentReady && !error && (!loading || wasNoRunsEmpty);
  if (!runMode && (noRunsEmptySticky.scopeKey !== noRunsScopeKey || noRunsEmptySticky.active !== showNoRunsEmpty)) {
    setNoRunsEmptySticky({ scopeKey: noRunsScopeKey, active: showNoRunsEmpty });
  }

  const { projectsLoaded, projectsLoadFailed } = data;
  if (!projectsLoaded) {
    // The startup projects load exhausted its retries: offer a retry instead
    // of an unrecoverable spinner (this early return sits above every other
    // error branch, so without this the page spins forever even after the
    // backend recovered). No hooks in either branch — the hook count across
    // the false -> true flip is pinned by tests.
    if (projectsLoadFailed) {
      return (
        <EmptyState
          title={t('overview.projectsLoadFailedTitle')}
          description={t('overview.projectsLoadFailedDesc')}
          actionLabel={t('overview.retry')}
          onAction={() => callbacks.onProjectsRetry?.()}
        />
      );
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
          {/* This `{null}` pins .dashboard-page to Fragment child index 1 in every
              early-return branch, matching the main return's two-child Fragment
              (loader + div) below -- so switching between branches reconciles
              against the same slot instead of remounting the subtree and
              replaying the fade-in. Don't remove it. */}
          {null}
          <div className={`dashboard-page dashboard-fade dashboard-ready${dashboardAppearClass}`}>
            <EmptyState
              title={t('overview.noLocalProjectsTitle')}
              description={t('overview.noLocalProjectsDesc')}
              actionLabel={t('overview.browseRemote')}
              onAction={() => onNavigate?.('projects')}
            />
          </div>
        </>
      );
    }
    return (
      <>
        {null}
        <div className={`dashboard-page dashboard-fade dashboard-ready${dashboardAppearClass}`}>
          <EmptyState
            title={t('overview.noProjectsTitle')}
            description={t('overview.noProjectsDesc')}
            actionLabel={t('overview.addProject')}
            onAction={() => onNavigate?.('projects')}
          />
        </div>
      </>
    );
  }
  if (!selectedProject) {
    return (
      <>
        {null}
        <div className={`dashboard-page dashboard-fade dashboard-ready${dashboardAppearClass}`}>
          <EmptyState
            title={t('overview.noProjectSelectedTitle')}
            description={t('overview.noProjectSelectedDesc')}
            actionLabel={t('overview.chooseProject')}
            onAction={() => onNavigate?.('projects')}
          />
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
            <LoadingScreen variant="inline" message={projectName ? t('overview.loadingProjectMsg', { name: projectName }) : undefined} />
          </div>
        </>
      );
    }
    return (
      <>
        {null}
        <div className={`dashboard-page dashboard-fade dashboard-ready${dashboardAppearClass}`}>
          <EmptyState
            title={t('overview.loadProjectFailedTitle')}
            description={error}
            actionLabel={t('overview.retry')}
            onAction={() => callbacks.onRetry?.()}
          />
        </div>
      </>
    );
  }
  if (showNoRunsEmpty) {
    // Covers both the settled no-runs state and a background refetch of an
    // empty project (isFetching true, dashboard still null -- previously a
    // visually blank .dashboard-page with no dim and no loader), plus the
    // post-eval selectedRun flip while wasNoRunsEmpty is latched (loading
    // true, dashboard still null): stay here, dimmed, until the payload
    // lands rather than swapping to the full inline loader and back.
    return (
      <>
        {null}
        <div className={`dashboard-page dashboard-fade dashboard-ready${dashboardAppearClass}${isFetching ? ' dashboard-refreshing' : ''}`}>
          <IncompleteSetupCard projectInfo={projectInfo} onComplete={handleSetupComplete} />
          <EmptyState
            title={t('overview.noEvalsTitle')}
            description={t('overview.noEvalsDesc', { name: projectName })}
            actionLabel={t('overview.startEvaluation')}
            onAction={() => onNavigate?.('evaluate')}
          />
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
            <LoadingScreen variant="inline" message={projectName ? t('overview.loadingProjectMsg', { name: projectName }) : undefined} />
          </div>
        </>
      );
    }
    return (
      <>
        {null}
        <div className={`dashboard-page dashboard-fade dashboard-ready${dashboardAppearClass}`}>
          <EmptyState
            title={t('overview.loadRunFailedTitle')}
            description={t('overview.loadRunFailedDesc')}
            actionLabel={t('overview.retry')}
            onAction={() => callbacks.onRetry?.()}
          />
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
