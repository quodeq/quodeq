import { shouldShowEvaluateButton, shouldShowProjectTabs, shouldShowCompareTab } from './appGating.js';
import { buildDashboardDataBundle, buildNavigationBundle } from './routes/renderers.jsx';

// Pure prop-builders for App.jsx's Sidebar/TopBar wiring, extracted
// verbatim from the inline JSX props so App.jsx itself stays a thin
// composition of state + these builders. No behavior change: every field
// below matches the object literal that used to sit directly on the JSX
// element.

export function buildSidebarProps({
  activeTab, navTab, projectsCount, selectedSource, hasCurrentProjectRuns, sharedProjectInfo,
  projects, sharedHasContent, resolvedDisplayName, headerMeta, version, sidebarCounts,
  lastEvalAt, isPinned, onPinChange,
}) {
  return {
    activeTab,
    onNavTab: navTab,
    hasEvaluations: projectsCount > 0,
    showProjectTabs: shouldShowProjectTabs({ selectedSource, hasCurrentProjectRuns, sharedProjectInfo }),
    showCompareTab: shouldShowCompareTab({ projects, sharedHasContent }),
    selectedSource,
    projectInfo: { displayName: resolvedDisplayName, meta: headerMeta },
    version,
    violationsCount: sidebarCounts.violationsCount,
    historyCount: sidebarCounts.historyCount,
    lastEvalAt,
    isPinned,
    onPinChange,
  };
}

export function buildTopBarProps({
  resolvedDisplayName, activeTab, serverConnected, sidebarProvider, sidebarModel, selectedSource,
  projectsCount, onEvaluateClick, evaluating, topbarRunProgress, navTab, setSidebarPinned,
  breadcrumb, mobileTitle, navStackLength, navPop, effectiveDark, toggleTheme,
}) {
  return {
    projectName: resolvedDisplayName,
    activeTab,
    serverConnected,
    serverUrl: typeof window !== 'undefined' ? window.location.origin : null,
    provider: sidebarProvider,
    model: sidebarModel,
    selectedSource,
    onEvaluate: shouldShowEvaluateButton(projectsCount, selectedSource) ? onEvaluateClick : null,
    evaluating,
    runProgress: topbarRunProgress,
    onProviderClick: () => navTab('settings'),
    onMenuToggle: () => setSidebarPinned((v) => !v),
    onSelectProject: () => navTab('projects'),
    breadcrumb,
    mobileTitle,
    canGoBack: navStackLength > 1,
    onBack: navPop,
    effectiveDark,
    onToggleTheme: toggleTheme,
  };
}

// The MainContent/route props bundle — extracted verbatim from App.jsx's
// inline object literal. Pure: every field is either passed straight
// through or built from an existing builder (buildDashboardDataBundle /
// buildNavigationBundle), no new derivation.
export function buildContentProps({
  state, sharedSignal, navTab, navStackLength, isEvaluating, showToast, setWizardEntry,
  dismissFinding, applyDelta, bumpDismissRefresh, dismissRefreshKey,
}) {
  return {
    dashboardData: buildDashboardDataBundle({ state, sharedHasContent: sharedSignal.hasContent }),
    navigation: buildNavigationBundle({
      state, navTab, navStackLength,
      isEvaluating, showToast, setWizardEntry,
      sharedHasContent: sharedSignal.hasContent,
    }),
    evaluation: state.evalLifecycle,
    serverHealth: { connected: state.serverConnected, setConnected: state.setServerConnected },
    settings: state.settings,
    refreshDashboard: state.refreshDashboard,
    // Debounced ACTIVE reconcile for suppression mutations (dismiss/restore/
    // delete) — see useDashboard.js. refreshDashboard's refetchType:'none'
    // only marks the cache stale; this actually refetches the always-mounted
    // Overview observer after the 1200ms window, so restore-all/delete-all
    // (whose response can't be patched via applyMutationDelta) and every
    // other suppression mutation converge without waiting for a project
    // switch.
    scheduleDashboardReconcile: state.scheduleDashboardReconcile,
    dismissFinding,
    // Patch the dashboard/scores caches from the dismiss response delta so the
    // Overview updates instantly. Additive — the refreshDashboard /
    // bumpDismissRefresh mechanisms below still run. The delta carries only the
    // mutation shape; the caller folds in the rescored dims from result.scores.
    applyDelta,
    bumpDismissRefresh,
    dismissRefreshKey,
  };
}
