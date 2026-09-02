import { shouldShowEvaluateButton, shouldShowProjectTabs, shouldShowCompareTab } from './appGating.js';

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
    onToggleTheme,
  };
}
