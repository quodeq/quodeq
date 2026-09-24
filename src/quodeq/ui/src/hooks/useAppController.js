import { useQueryClient } from '@tanstack/react-query';
import { applyMutationDelta } from '../api/applyMutationDelta.js';
import {
  computeIsEvaluating, useAppBootExtras, useAppWizardBounce, useAppDerived, useAppEvalProgress,
  useSidebarProviderSelection, useAppStartupGate, useAppNavigationEffects, useSelectedProjectSyncEffects,
} from './useAppShellHooks.js';
import { useAssistantActionAppliedEffect } from './useAppEffects.js';

/**
 * Boot-time extras plus the dismiss-delta bridge shared by the manual dismiss
 * handlers (dismissWithReconcile callers in routes/renderers.jsx) and the
 * assistant's action-applied effect: patches the dashboard/scores caches from
 * a dismiss response's delta so the Overview updates instantly instead of
 * waiting on a refetch.
 */
export function useAppDismissBridge(state) {
  const queryClient = useQueryClient();
  const boot = useAppBootExtras();
  const applyDelta = (project, scores, delta) =>
    applyMutationDelta(queryClient, project, delta && { ...delta, dimensions: scores?.dimensions });
  useAssistantActionAppliedEffect({
    applyDelta,
    bumpDismissRefresh: boot.bumpDismissRefresh,
    scheduleReconcileForApply: state.scheduleDashboardReconcile,
    selectedProject: state.selectedProject,
  });
  return { ...boot, applyDelta };
}

/**
 * Wizard lifecycle, sidebar/startup chrome, the derived view data and the
 * topbar run progress, in the order App has always called them.
 */
export function useAppChrome({ state, sharedSignal }) {
  const selectedProjectInfo = state.projects?.find((p) => (p.id || p.name) === state.selectedProject) || null;
  const isEvaluating = computeIsEvaluating(state);
  const wizard = useAppWizardBounce({ state, selectedProjectInfo, isEvaluating, sharedSignal });
  const { activePage, navSwapAt, navTab, activeTab } = state;
  const sidebar = useSidebarProviderSelection();
  const startup = useAppStartupGate({ state, activeTab });
  useAppNavigationEffects({ state, activeTab, navTab, sharedSignal });
  useSelectedProjectSyncEffects(state.selectedProject);
  const derived = useAppDerived({ state, navTab, navSwapAt, activePage });
  const topbarRunProgress = useAppEvalProgress({ state, isEvaluating });
  return { selectedProjectInfo, isEvaluating, ...wizard, ...sidebar, ...startup, ...derived, topbarRunProgress };
}
