import { useApi } from './api/ApiContext.jsx';
import { useAppState } from './hooks/useAppState.js';
import { useAppAssistant } from './hooks/useAppShellHooks.js';
import { useAppDismissBridge, useAppChrome } from './hooks/useAppController.js';
import { buildAppShell } from './appShellProps.js';
import AppMain from './AppMain.jsx';

// Route rendering, gating policies, wizard lifecycle, assistant glue and
// startup chrome moved to their own modules (see routes/renderers.jsx,
// appGating.js, features/onboarding/useWizardLifecycle.js,
// features/assistant/assistantAppBridge.js, hooks/useStartupTheme.js).
// Re-exported here so the existing import surface — tests pin these
// contracts via App.jsx — stays stable.
export {
  isSharedSource, buildEvalPrincipal, ROUTE_RENDERERS,
  resolveSelectionAfterSharedDisconnect, shouldWallEmptyProjects,
  buildDashboardDataBundle, buildNavigationBundle,
} from './routes/renderers.jsx';
export {
  shouldBounceToEvaluate, shouldShowEvaluateButton, resolveProjectDisplayName,
  shouldShowProjectTabs, selectSidebarCounts, shouldRedirectToRemoteRepositories,
} from './appGating.js';
export {
  buildAssistantSessionPayload, buildAssistantActionAppliedHandler,
} from './features/assistant/assistantAppBridge.js';
export { buildWizardHandlers, shouldAutoOpenOnboardingWizard } from './features/onboarding/useWizardLifecycle.js';
export { shouldShowStartupLoader } from './hooks/useStartupTheme.js';

export default function App() {
  const { dismissFinding } = useApi();
  const state = useAppState();
  const { sharedSignal, sidebarPinned, setSidebarPinned, dismissRefreshKey, bumpDismissRefresh, applyDelta } =
    useAppDismissBridge(state);
  const APP_VERSION = state.serverVersion;

  const { showToast, assistantCtx } = useAppAssistant(state);

  const {
    selectedProjectInfo, isEvaluating, wizardEntry, setWizardEntry, wizardHandlers, hasCurrentProjectRuns,
    sidebarProvider, sidebarModel, showStartupLoader,
    effectiveDark, toggleTheme, filteredTrend, filteredAccumulated, breadcrumbSiblingsFor, topbarRunProgress,
  } = useAppChrome({ state, sharedSignal });

  const { activePage, navStack, navPop, navGoTo, navTab, activeTab } = state;

  const shell = buildAppShell({
    state, sharedSignal, navTab, navStack, activeTab, activePage, isEvaluating, showToast, setWizardEntry,
    dismissFinding, applyDelta, bumpDismissRefresh, dismissRefreshKey, selectedProjectInfo, hasCurrentProjectRuns,
    assistantCtx, APP_VERSION, sidebarPinned, setSidebarPinned, sidebarProvider, sidebarModel, topbarRunProgress,
    navGoTo, navPop, breadcrumbSiblingsFor, effectiveDark, toggleTheme, showStartupLoader, wizardEntry, wizardHandlers,
    filteredAccumulated, filteredTrend,
  });

  return <AppMain shell={shell} />;
}
