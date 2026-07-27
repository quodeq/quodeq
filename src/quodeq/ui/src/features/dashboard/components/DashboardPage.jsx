import { useEffect, useMemo, useRef, useState } from 'react';
import DimensionCard from './DimensionCard.jsx';
import AccumulatedOverviewPanel from './AccumulatedOverviewPanel.jsx';
import RunOverviewPanel from './RunOverviewPanel.jsx';
import IncompleteSetupCard from './IncompleteSetupCard.jsx';
import LoadingScreen from '../../../components/LoadingScreen.jsx';
import EmptyState from '../../../components/EmptyState.jsx';

function NoCompletedEvalPanel({ availableRuns = [], onNavigate, selectedSource }) {
  const hasRunning = availableRuns.some((r) => r?.status === 'in_progress');
  if (hasRunning) {
    // First-ever evaluation is still running. There's no prior data to
    // show, but we still avoid claiming the project has "no" evaluations
    // — they just haven't finished yet.
    return (
      <EmptyState
        title="First evaluation in progress"
        description="The overview will fill in once a run finishes. You can watch dimensions complete in History."
        actionLabel="Open history"
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
        title="No completed evaluation yet"
        description="no completed evaluation in this remote project yet"
      />
    );
  }
  return (
    <EmptyState
      title="No completed evaluation yet"
      description="Previous attempts didn't finish cleanly. Start a new evaluation to populate the overview."
      actionLabel="Start evaluation"
      onAction={() => onNavigate?.('evaluate')}
    />
  );
}

function DashboardContent({ runMode, ready, data, focus, callbacks }) {
  const { dashboard, selectedRunId, accumulated, accumulatedDimensions, availableRuns, dailyRuns, overviewRunIndex, selectedProject, projectInfo, granularity, selectedSource, scoresPending } = data;
  const { dimension: focusedDimension, setDimension: setFocusedDimension, dimensionData: focusedDimensionData } = focus;
  const { onRunSelect, onDimensionCardClick, onAccumulatedDimensionClick, onFileClick, onNavigate, onGranularityChange } = callbacks;
  // Readiness is decided once, by the page (DashboardPage's isLoading/contentReady
  // rule) -- this never re-derives it from `accumulated` on its own, so there is
  // exactly one place a loader can be mounted from.
  if (!ready) {
    return <LoadingScreen variant="inline" />;
  }
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
            Show all
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
        scoresPending,
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
  const { selectedProject, selectedSource, selectedRun, projects = [], sharedProjectInfo = null, dashboard, accumulated, loading, isFetching, scoresPending = false, error, availableRuns = [], dailyRuns, overviewRunIndex = 0, granularity = 'day', onGranularityChange, sharedHasContent = false } = data;
  const projectInfo = selectDashboardProjectInfo({ selectedSource, projects, selectedProject, sharedProjectInfo });
  const { onNavigate, onRunSelect, onProjectsReload } = callbacks;
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
  useEffect(() => {
    if (contentReady || !dashboard) { setGraceElapsed(false); return undefined; }
    const timer = setTimeout(() => setGraceElapsed(true), 700);
    return () => clearTimeout(timer);
  }, [contentReady, dashboard]);

  const { projectsLoaded } = data;
  if (!projectsLoaded) return <LoadingScreen />;
  if (projects.length === 0 && selectedSource !== 'shared') {
    // Zero local projects. When the connected shared repo has published
    // content, the useful next step is browsing it (read-only until pulled)
    // -- not necessarily scanning something locally. Both CTAs land on the
    // repositories tab; the copy is what differs.
    if (sharedHasContent) {
      return (
        <EmptyState
          title="No local projects yet"
          description="Your team’s online repository has published projects you can browse without scanning anything locally."
          actionLabel="Browse remote repositories"
          onAction={() => onNavigate?.('projects')}
        />
      );
    }
    return (
      <EmptyState
        title="No projects yet"
        description="Add a project to start analyzing code quality."
        actionLabel="Add a project"
        onAction={() => onNavigate?.('projects')}
      />
    );
  }
  if (!selectedProject) {
    return (
      <EmptyState
        title="No project selected"
        description="Pick a project to view its overview."
        actionLabel="Choose project"
        onAction={() => onNavigate?.('projects')}
      />
    );
  }
  const projectName = projectInfo?.displayName || projectInfo?.name || selectedProject;
  if (!loading && !isFetching && !dashboard) {
    // A failed fetch also lands here (dashboard === null, queries settled).
    // It must render as an error: claiming "No evaluations yet" on a
    // 404/500/timeout tells the user their existing evaluations are gone.
    if (error) {
      return (
        <div className="dashboard-page dashboard-fade dashboard-ready">
          <EmptyState
            title="Couldn't load this project"
            description={error}
            actionLabel="Retry"
            onAction={() => callbacks.onRetry?.()}
          />
        </div>
      );
    }
    return (
      <div className="dashboard-page dashboard-fade dashboard-ready">
        <IncompleteSetupCard projectInfo={projectInfo} onComplete={handleSetupComplete} />
        <EmptyState
          title="No evaluations yet"
          description={`Run an evaluation for ${projectName} to populate this page.`}
          actionLabel="Start evaluation"
          onAction={() => onNavigate?.('evaluate')}
        />
      </div>
    );
  }

  // Hold the full LoadingScreen until the content is ready, so we don't fade in
  // a half-drawn page and then pop the real content in a beat later (the
  // first-load flicker). BUT a cold score cache can take several seconds to
  // rebuild (e.g. right after a dismiss/restore/formula change invalidates it);
  // sitting on a blank spinner that whole time reads as "not opening". So once
  // the dashboard payload is in and the grace has elapsed (graceElapsed, set
  // above), fall back to the partial page (frame + a content spinner) so a slow
  // load shows progress instead of a hang. The grace comfortably exceeds a warm
  // load, so the fast path still gets one clean transition.
  const isLoading = loading && !contentReady && !(dashboard && graceElapsed);
  // True while a *background* fetch is running but we're already showing
  // data (placeholderData kept the previous run on screen during a switch).
  // The page dims itself slightly so the user sees "still working" without
  // the jarring full-screen LoadingScreen.
  const isRefreshing = isFetching && !!dashboard && !isLoading;
  return (
    <>
      {/* Sibling to .dashboard-page, not a child of it: that div carries the
          `dashboard-loading` opacity-.4 class for exactly as long as this loader
          is shown, and a loader dimmed by its own "still loading" state renders
          its logo at an unreadable 6% opacity. Names the project being loaded --
          a project switch now clears the old payload (placeholderData is
          project-scoped -- see samePlaceholderScope), so this spinner is what
          the user sees right after picking a project; saying which one makes
          the wait legible instead of looking like the page hung. */}
      {isLoading && <LoadingScreen variant="inline" message={projectName ? `Loading ${projectName}…` : undefined} />}
      <div className={`dashboard-page dashboard-fade ${isLoading ? 'dashboard-loading' : 'dashboard-ready'}${isRefreshing ? ' dashboard-refreshing' : ''}`}>
        <IncompleteSetupCard projectInfo={projectInfo} onComplete={handleSetupComplete} />
        {error && <p className="inline-error">Failed to load dashboard data. Please try again.</p>}
        {dashboard && !isLoading && (
          <DashboardContent
            runMode={runMode}
            ready={contentReady}
            data={{ dashboard, selectedRunId, accumulated, accumulatedDimensions, availableRuns, dailyRuns, overviewRunIndex, selectedProject, projectInfo, granularity, selectedSource, scoresPending }}
            focus={{ dimension: focusedDimension, setDimension: setFocusedDimension, dimensionData: focusedDimensionData }}
            callbacks={{ onRunSelect, onDimensionCardClick: handlers.handleDimensionCardClick, onAccumulatedDimensionClick: handlers.handleAccumulatedDimensionClick, onFileClick: handlers.handleFileClick, onNavigate, onGranularityChange }}
          />
        )}
      </div>
    </>
  );
}
