import { useQueryClient } from '@tanstack/react-query';
import { applyMutationDelta } from '../api/applyMutationDelta.js';
import { recordDismissedEntry } from '../api/dismissedListCache.js';
import { PROJECT_SOURCE } from '../vocab/projectSource.js';
import {
  computeIsEvaluating, useAppBootExtras, useAppWizardBounce, useAppDerived,
  useSidebarProviderSelection, useAppStartupGate, useAppNavigationEffects, useSelectedProjectSyncEffects,
  useVisibleStandardsFiltered,
} from './useAppShellHooks.js';
import { useAssistantActionAppliedEffect } from './useAppEffects.js';
import { findProject } from '../utils/projectIdentity.js';
import { selectLandedProject } from './selectLandedProject.js';
import { shouldShowEvaluate } from '../appGating.js';
import { useCloneStatus } from './useCloneStatus.js';

/**
 * Boot-time extras plus the dismiss-delta bridge shared by the manual dismiss
 * handlers (dismissWithReconcile callers in routes/renderers.jsx) and the
 * assistant's action-applied effect: patches the dashboard/scores caches from
 * a dismiss response's delta so the Overview updates instantly instead of
 * waiting on a refetch.
 */
export function useAppDismissBridge(state) {
  const queryClient = useQueryClient();
  // A clone that lands becomes the selected project on the Repositories tab
  // (or when nothing is selected yet); elsewhere the card simply appears.
  const boot = useAppBootExtras({ onCloneLanded: (slot) => selectLandedProject(state, slot.projectId) });
  const applyDelta = (project, scores, delta) =>
    applyMutationDelta(queryClient, project, delta && { ...delta, dimensions: scores?.dimensions });
  // A dismiss is local-only, so the entry always lands in the local list.
  const recordDismissed = (project, entry) =>
    recordDismissedEntry(queryClient, project, PROJECT_SOURCE.LOCAL, entry);
  useAssistantActionAppliedEffect({
    applyDelta,
    recordDismissed,
    scheduleReconcileForApply: state.scheduleDashboardReconcile,
    selectedProject: state.selectedProject,
  });
  return { ...boot, applyDelta, recordDismissed };
}

/**
 * Wizard lifecycle, sidebar/startup chrome and the derived view data, in the
 * order App has always called them.
 */
export function useAppChrome({ state, sharedSignal }) {
  const selectedProjectInfo = findProject(state.projects, state.selectedProject);
  const isEvaluating = computeIsEvaluating(state);
  // Evaluate exists only for a selected local project that has landed; a
  // project whose clone is still running has no folder to evaluate yet.
  const clone = useCloneStatus();
  const showEvaluate = shouldShowEvaluate({
    selectedSource: state.selectedSource, selectedProjectInfo, cloneSlot: clone.active ? clone.slot : null,
  });
  const wizard = useAppWizardBounce({ state, isEvaluating, sharedSignal });
  const { activePage, navSwapAt, navTab, activeTab } = state;
  const sidebar = useSidebarProviderSelection();
  const startup = useAppStartupGate({ state, activeTab });
  useAppNavigationEffects({ state, activeTab, navTab, showEvaluate, sharedSignal });
  useSelectedProjectSyncEffects(state.selectedProject);
  const { filteredTrend, filteredAccumulated } = useVisibleStandardsFiltered(state);
  const derived = useAppDerived({ state, navTab, navSwapAt, activePage, filteredTrend, filteredAccumulated });
  return { selectedProjectInfo, showEvaluate, isEvaluating, ...wizard, ...sidebar, ...startup, ...derived };
}
