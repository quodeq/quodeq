import { useEffect, useRef, useState } from 'react';

// Matches the .dashboard-appear animation length (dashboard.css) -- the
// class is held for this long so re-renders can't cut the fade short.
const DASHBOARD_APPEAR_MS = 400;

// What each view needs before it can render real content: run detail only
// needs the dashboard payload; the Overview also needs the scores-derived
// `accumulated` block. This is the single readiness rule for the whole page
// -- DashboardContent is only mounted once it holds, and never re-derives
// its own readiness from `accumulated`, so there is exactly one loader
// decision instead of two that can disagree.
//
// Grace state for the slow/cold-load fallback (consumed by isLoading below).
// Reset synchronously during render, not from an effect: contentReady
// flipping true (or dashboard disappearing) and graceElapsed resetting are
// the same logical transition. Doing it from an effect meant a stale
// intermediate commit (graceElapsed still true) landed first and ran ITS
// OWN effects -- including the appear-fade latch's ref write further down
// -- before this effect got a chance to correct it; a second, cascading
// commit then found the latch already spent and dropped the fade it had
// just armed. Resetting here settles the transition in a single commit,
// before any effects run at all -- same "adjust state during render"
// pattern as the sticky no-runs latch below, safe under StrictMode's
// double-render for the same reason: idempotent once the condition clears.
//
// Hold the full LoadingScreen until the content is ready, so we don't fade in
// a half-drawn page and then pop the real content in a beat later (the
// first-load flicker). BUT a cold score cache can take several seconds to
// rebuild (e.g. right after a dismiss/restore/formula change invalidates it);
// sitting on a blank spinner that whole time reads as "not opening". So once
// the dashboard payload is in and the grace has elapsed (graceElapsed, set
// above), fall back to the partial page (frame + a content spinner) so a slow
// load shows progress instead of a hang. The grace comfortably exceeds a warm
// load, so the fast path still gets one clean transition.
function useContentReadiness(runMode, dashboard, accumulated, loading) {
  const contentReady = runMode ? !!dashboard : (!!dashboard && !!accumulated);
  const [graceElapsed, setGraceElapsed] = useState(false);
  if (graceElapsed && (contentReady || !dashboard)) setGraceElapsed(false);
  useEffect(() => {
    if (contentReady || !dashboard) return undefined;
    const timer = setTimeout(() => setGraceElapsed(true), 700);
    return () => clearTimeout(timer);
  }, [contentReady, dashboard]);

  const isLoading = loading && !contentReady && !(dashboard && graceElapsed);

  // Overview only (!runMode): both loader windows above (isLoading itself,
  // and the grace-fallback window once dashboard has landed but accumulated
  // hasn't) render one continuous OverviewSkeleton instead of a LoadingScreen.
  const showOverviewSkeleton = !runMode && !!(isLoading || (dashboard && !isLoading && !contentReady));

  return { contentReady, isLoading, showOverviewSkeleton };
}

// Fade-once latch: `dashboard-fadein` should play when the page's content
// first appears for this project/source/run context, not on every
// loading<->ready flip within it (grace-fallback then content-ready, an
// error settling, the no-runs sticky state handing off to real content).
// The animation itself lives on a separate `dashboard-appear` class (kept
// apart from the `dashboard-ready` state class) so re-adding `dashboard-ready`
// alone -- e.g. dropping `dashboard-refreshing` -- never replays it. The ref
// is only written from an effect (post-commit), never during render:
// mutating it inline would make the appear decision depend on how many times
// React happens to invoke this render (StrictMode double-invokes it in dev).
// `!showOverviewSkeleton` gates both the read and the write: without it, the
// grace-elapsed flip (isLoading true -> false while the Overview's skeleton
// keeps showing, accumulated still pending) would (a) play the 400ms fade
// over a skeleton that was already fully visible and unchanged -- a flash
// the skeleton is supposed to avoid -- and (b) spend the latch early, so the
// *real* content that mounts once accumulated lands would get no fade at
// all. showOverviewSkeleton is false for every other branch (runMode, error,
// empty states, sticky no-runs), so this is a no-op there.
function useDashboardAppear(dashboardAppearKey, isLoading, showOverviewSkeleton) {
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
  return (dashboardAppearNow || appearHeld) ? ' dashboard-appear' : '';
}

// Sticky "no evaluations yet" latch: once that empty state is showing for
// this project+source, stay on it through a subsequent load (the post-eval
// selectedRun flip -- new dashboard key, loading true, dashboard still
// null) instead of popping to the full inline loader for a beat. Keyed off
// project+source so a project switch never inherits the previous project's
// stickiness. runMode never shows this empty state, so it's excluded
// outright -- and a runMode render must never touch the latch at all:
// App.jsx doesn't always remount DashboardPage between the Overview and a
// run detail view for the same project+source, so writing `active: false`
// here on a runMode pass would clear a legitimately-active Overview latch
// out from under it.
//
// Latch on !contentReady, not !dashboard: releasing the latch the moment
// the dashboard payload lands (but before accumulated does) reopened the
// same pop this latch exists to close, just narrower -- empty(dimmed) ->
// inline spinner -> content instead of loader -> content. contentReady
// already folds in the accumulated wait for the Overview (runMode is
// excluded from this branch outright, so its own dashboard-only readiness
// never applies here), so holding the empty state open until BOTH payloads
// land closes the gap without a separate flag to keep in sync.
function useNoRunsSticky(runMode, contentReady, error, loading, noRunsScopeKey) {
  const [noRunsEmptySticky, setNoRunsEmptySticky] = useState({ scopeKey: noRunsScopeKey, active: false });
  const wasNoRunsEmpty = noRunsEmptySticky.scopeKey === noRunsScopeKey && noRunsEmptySticky.active;
  const showNoRunsEmpty = !runMode && !contentReady && !error && (!loading || wasNoRunsEmpty);
  if (!runMode && (noRunsEmptySticky.scopeKey !== noRunsScopeKey || noRunsEmptySticky.active !== showNoRunsEmpty)) {
    setNoRunsEmptySticky({ scopeKey: noRunsScopeKey, active: showNoRunsEmpty });
  }
  return showNoRunsEmpty;
}

// Composed grace/appear/sticky-latch state machine for DashboardPage. Calls
// its three sub-hooks unconditionally, every render, in the same order they
// ran when this was inline in DashboardPage -- preserving both the render-
// phase state adjustments (grace reset, sticky-latch write) and the
// useState/useEffect/useRef call order StrictMode's double-invocation
// depends on.
export function useDashboardPageState({ runMode, dashboard, accumulated, loading, error, selectedProject, selectedSource, selectedRunId }) {
  const { contentReady, isLoading, showOverviewSkeleton } = useContentReadiness(runMode, dashboard, accumulated, loading);
  // Keyed like noRunsScopeKey below, but the run is folded in too so a run
  // switch on run-detail gets its own fade.
  const dashboardAppearKey = `${selectedProject}::${selectedSource}::${runMode ? selectedRunId : 'overview'}`;
  const dashboardAppearClass = useDashboardAppear(dashboardAppearKey, isLoading, showOverviewSkeleton);
  const noRunsScopeKey = `${selectedProject}::${selectedSource}`;
  const showNoRunsEmpty = useNoRunsSticky(runMode, contentReady, error, loading, noRunsScopeKey);
  return { contentReady, isLoading, showOverviewSkeleton, dashboardAppearClass, showNoRunsEmpty };
}
