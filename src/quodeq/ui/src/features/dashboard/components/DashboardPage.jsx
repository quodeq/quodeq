import { useEffect, useMemo } from 'react';
import { useDashboardPageState } from '../hooks/useDashboardPageState.js';
import { useDashboardHandlers } from '../hooks/useDashboardHandlers.js';
import { useFocusedDimension } from '../hooks/useFocusedDimension.js';
import { preloadRunHistoryPanel } from './AccumulatedOverviewPanel.jsx';
import { renderDashboardGate } from './dashboardGate.jsx';
import { renderDashboardBody } from './dashboardBody.jsx';
import { ProjectsLoadFailedState } from './DashboardPageEmptyStates.jsx';

// ---------------------------------------------------------------------------
// DashboardPage — body only, header is rendered by App.jsx
// Top-level page component that receives all dashboard state and callbacks
// directly from App; the high prop count is intentional and not worth splitting.
// The ready-state body (dashboardBody.jsx), the early-return ladder
// (dashboardGate.jsx) and the click-handler memo (useDashboardHandlers) live in
// sibling files. Both render modules are plain functions, never components:
// each branch's wrapper element type/position is load-bearing for the
// fade/appear latch (see useDashboardPageState) and the .dashboard-page node's
// identity across branch swaps is test-pinned, which only holds while every
// branch returns its tree from this one position in the render.
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

// After a successful clone-on-add migration the project's repository_info.json
// has been rewritten with location: "local". Refetch the projects list so the
// sidebar/header reflect the new state. Fall back to a full reload if no
// refetch hook is plumbed through.
function makeSetupCompleteHandler(onProjectsReload) {
  return () => {
    if (typeof onProjectsReload === 'function') onProjectsReload();
    else if (typeof window !== 'undefined') window.location.reload();
  };
}

export default function DashboardPage({ data = {}, callbacks = {}, runMode = false }) {
  const { selectedProject, selectedSource, selectedRun, projects, sharedProjectInfo, dashboard, accumulated, loading, error, projectsLoaded, projectsLoadFailed } = data;
  const projectInfo = selectDashboardProjectInfo({ selectedSource, projects, selectedProject, sharedProjectInfo });
  const onSetupComplete = makeSetupCompleteHandler(callbacks.onProjectsReload);
  // Warm the score-history chunk while the boot loader / skeleton is still
  // up: the chart is a separate lazy chunk, and without this the first
  // data-bearing mount commits its placeholder for a beat inside otherwise
  // real content — the exact flash the startup hold exists to remove.
  useEffect(() => { preloadRunHistoryPanel(); }, []);
  const selectedRunId = dashboard?.selectedRun?.runId || selectedRun;
  const [focusedDimension, setFocusedDimension] = useFocusedDimension(selectedRunId);
  // Accumulated dimensions are pre-rescored from the server — no client-side merge needed
  const accumulatedDimensions = useMemo(() => accumulated?.dimensions || [], [accumulated]);
  const focusedDimensionData = useMemo(() => focusedDimension ? (dashboard?.dimensions || []).find((d) => d.dimension === focusedDimension) || null : null, [focusedDimension, dashboard]);
  const handlers = useDashboardHandlers(callbacks.onNavigate, dashboard);

  // These hooks MUST stay above the early returns below — calling them after a
  // conditional return changes the hook count between renders (React error
  // #310, a blank-crash on load). The grace/appear/sticky-latch state machine
  // is extracted into useDashboardPageState (hooks/useDashboardPageState.js);
  // its sub-hooks run in the exact order they did when inline here, so the
  // render-phase state adjustments (grace reset, sticky-latch write) and the
  // StrictMode double-invocation semantics they depend on are unchanged.
  const pageState = useDashboardPageState({
    runMode, dashboard, accumulated, loading, error, selectedProject, selectedSource, selectedRunId,
  });

  if (!projectsLoaded) {
    // The startup projects load exhausted its retries: offer a retry instead
    // of an unrecoverable spinner (this early return sits above every other
    // error branch, so without this the page spins forever even after the
    // backend recovered). No hooks in either branch — the hook count across
    // the false -> true flip is pinned by tests.
    if (projectsLoadFailed) return <ProjectsLoadFailedState onRetry={callbacks.onProjectsRetry} />;
    // The app-level FadingLoadingScreen overlay covers this state; render
    // nothing here so the loader lives at one stable spot and can fade out.
    return null;
  }
  const projectName = projectInfo?.displayName || projectInfo?.name || selectedProject;
  const gate = renderDashboardGate({ data, callbacks, runMode, projectName, projectInfo, pageState, onSetupComplete });
  if (gate) return gate;
  const focus = { dimension: focusedDimension, setDimension: setFocusedDimension, dimensionData: focusedDimensionData };
  return renderDashboardBody({ data, callbacks, runMode, projectName, projectInfo, pageState, focus, handlers, accumulatedDimensions, selectedRunId, onSetupComplete });
}
