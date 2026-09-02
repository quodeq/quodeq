import { useQueryClient } from '@tanstack/react-query';
import { useApi } from './api/ApiContext.jsx';
import { applyMutationDelta } from './api/applyMutationDelta.js';
import { useAppState } from './hooks/useAppState.js';
import {
  computeIsEvaluating, useAppBootExtras, useAppAssistant, useAppWizardBounce,
  useAppNavBoot, useAppDerived, useAppEvalProgress,
} from './hooks/useAppShellHooks.js';
import {
  buildAssistantSessionPayload, buildAssistantActionAppliedHandler,
} from './features/assistant/assistantAppBridge.js';
import { useAssistantActionAppliedEffect } from './hooks/useAppEffects.js';
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
  const queryClient = useQueryClient();
  const state = useAppState();
  const { sharedSignal, sidebarPinned, setSidebarPinned, dismissRefreshKey, bumpDismissRefresh } = useAppBootExtras();
  const APP_VERSION = state.serverVersion;
  const selectedProjectInfo = state.projects?.find((p) => (p.id || p.name) === state.selectedProject) || null;
  const {
    scheduleDashboardReconcile: scheduleReconcileForApply,
    selectedProject,
  } = state;
  // Shared with the manual dismiss handlers (dismissWithReconcile callers in
  // routes/renderers.jsx). Patches the dashboard/scores caches from a dismiss
  // response's delta so the Overview updates instantly instead of waiting on
  // a refetch.
  const applyDelta = (project, scores, delta) =>
    applyMutationDelta(queryClient, project, delta && { ...delta, dimensions: scores?.dimensions });
  useAssistantActionAppliedEffect({
    applyDelta, bumpDismissRefresh, scheduleReconcileForApply, selectedProject,
  });

  const { showToast, assistantCtx } = useAppAssistant(state);

  const isEvaluating = computeIsEvaluating(state);

  const { wizardEntry, setWizardEntry, wizardHandlers, hasCurrentProjectRuns } = useAppWizardBounce({
    state, selectedProjectInfo, isEvaluating, sharedSignal,
  });

  const { activePage, navStack, navPop, navGoTo, navSwapAt, navTab, activeTab } = state;
  const { sidebarProvider, sidebarModel, showStartupLoader } = useAppNavBoot({ state, activeTab, navTab, sharedSignal });

  const { currentDayLabel, effectiveDark, toggleTheme, filteredTrend, filteredAccumulated, breadcrumbSiblingsFor } =
    useAppDerived({ state, navTab, navSwapAt, activePage });

  const topbarRunProgress = useAppEvalProgress({ state, isEvaluating });

  const shell = buildAppShell({
    state, sharedSignal, navTab, navStack, activeTab, activePage, isEvaluating, showToast, setWizardEntry,
    dismissFinding, applyDelta, bumpDismissRefresh, dismissRefreshKey, selectedProjectInfo, hasCurrentProjectRuns,
    assistantCtx, APP_VERSION, sidebarPinned, setSidebarPinned, sidebarProvider, sidebarModel, topbarRunProgress,
    navGoTo, navPop, breadcrumbSiblingsFor, effectiveDark, toggleTheme, showStartupLoader, wizardEntry, wizardHandlers,
    filteredAccumulated, filteredTrend,
  });

  return <AppMain shell={shell} />;
}
