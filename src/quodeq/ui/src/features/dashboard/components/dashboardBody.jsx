import IncompleteSetupCard from './IncompleteSetupCard.jsx';
import OverviewSkeleton from './OverviewSkeleton.jsx';
import LoadingScreen from '../../../components/LoadingScreen.jsx';
import WarmupNotice from '../../../components/WarmupNotice.jsx';
import { t } from '../../../strings/index.js';
import DashboardContent from './DashboardContent.jsx';
import { dashboardPageClassName } from './dashboardGate.jsx';

// The ready-state render of DashboardPage. A plain function, not a component,
// for the same reason the gate ladder is: the .dashboard-page node's identity
// across branch transitions is test-pinned (DashboardPage.fadeOnceIdentity),
// and it only survives while every branch returns its tree from the one
// position in DashboardPage's render.

function renderReadyContent({ data, callbacks, runMode, projectInfo, selectedRunId, accumulatedDimensions, focus, handlers }) {
  const { dashboard, accumulated, availableRuns = [], dailyRuns, overviewRunIndex = 0, selectedProject, granularity = 'day', selectedSource, scoresPending = false, customFormula = false, onGranularityChange } = data;
  const { onRunSelect, onNavigate } = callbacks;
  return (
    <DashboardContent
      runMode={runMode}
      data={{ dashboard, selectedRunId, accumulated, accumulatedDimensions, availableRuns, dailyRuns, overviewRunIndex, selectedProject, projectInfo, granularity, selectedSource, scoresPending, customFormula }}
      focus={focus}
      callbacks={{ onRunSelect, onDimensionCardClick: handlers.handleDimensionCardClick, onAccumulatedDimensionClick: handlers.handleAccumulatedDimensionClick, onFileClick: handlers.handleFileClick, onNavigate, onGranularityChange }}
    />
  );
}

/**
 * @param {object} ctx
 * @param {object} ctx.data dashboard state slice (dashboard, error, isFetching,
 *   warmup, accumulated, availableRuns, dailyRuns, overviewRunIndex,
 *   selectedProject, granularity, selectedSource, scoresPending, customFormula)
 * @param {object} ctx.callbacks passed through to DashboardContent (onRunSelect,
 *   onNavigate, onGranularityChange)
 * @param {boolean} ctx.runMode
 * @param {object|null} ctx.projectInfo
 * @param {string} ctx.projectName
 * @param {object} ctx.pageState from useDashboardPageState (contentReady,
 *   isLoading, showOverviewSkeleton, dashboardAppearClass)
 * @param {object} ctx.focus current focused dimension (dimension, setDimension,
 *   dimensionData)
 * @param {object} ctx.handlers click handlers from useDashboardHandlers
 *   (handleDimensionCardClick, handleAccumulatedDimensionClick, handleFileClick)
 * @param {Array} ctx.accumulatedDimensions pre-rescored accumulated dimensions
 * @param {string} [ctx.selectedRunId]
 * @param {() => void} ctx.onSetupComplete
 */
export function renderDashboardBody(ctx) {
  const { data, runMode, projectInfo, projectName, pageState, onSetupComplete } = ctx;
  const { dashboard, error, isFetching, warmup = null } = data;
  const { contentReady, isLoading, showOverviewSkeleton, dashboardAppearClass } = pageState;
  // True while a *background* fetch is running but we're already showing
  // data (placeholderData kept the previous run on screen during a switch).
  // The page dims itself slightly so the user sees "still working" without
  // the jarring full-screen LoadingScreen.
  const isRefreshing = isFetching && !!dashboard && !isLoading;
  // showOverviewSkeleton comes from useDashboardPageState (beside the appear
  // latch, which needs it too) -- from the user's perspective this covers both
  // loader windows as one continuous OverviewSkeleton, no handoff between them.
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
      <div className={dashboardPageClassName({ appearClass: dashboardAppearClass, dimmed: isDimmed, refreshing: isRefreshing })}>
        <IncompleteSetupCard projectInfo={projectInfo} onComplete={onSetupComplete} />
        {error && <p className="inline-error">{t('overview.loadFailed')}</p>}
        {showOverviewSkeleton && <WarmupNotice warmup={warmup} />}
        {showOverviewSkeleton && <OverviewSkeleton projectName={projectName} />}
        {/* No runMode equivalent of the Overview's grace-fallback loader: in
            runMode contentReady is `!!dashboard`, so the instant dashboard lands
            contentReady is already true -- there's no window where dashboard is
            in but content isn't ready yet. The `isLoading && runMode`
            LoadingScreen above is the only loader runMode needs. */}
        {dashboard && contentReady && renderReadyContent(ctx)}
      </div>
    </>
  );
}
