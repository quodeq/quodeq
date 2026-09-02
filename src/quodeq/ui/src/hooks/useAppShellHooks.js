import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSharedContentSignal } from '../features/dashboard/hooks/useSharedProjects.js';
import { useEvaluationProgress } from '../features/evaluation/hooks/useEvaluationProgress.js';
import { computeOverallProgress } from '../features/evaluation/components/scanProgressTotals.js';
import { readActiveProviderSelection, readActiveProviderModel } from '../utils/effectiveProviderSettings.js';
import { formatDayLabel } from './useAppState.js';
import { useNativeNavBridge } from './useNativeNavBridge.js';
import { useStartupTheme, useStartupLoader } from './useStartupTheme.js';
import { useWizardLifecycle } from '../features/onboarding/useWizardLifecycle.js';
import { warmOverviewChunks } from '../bootChunks.js';
import { readVisibleStandardIds } from '../utils/visibleStandards.js';
import { filterTrendByVisibleStandards, filterAccumulatedByVisibleStandards } from '../utils/scoreFiltering.js';
import { useSidePane } from '../features/side-pane/index.js';
import { useAssistantDrawer } from '../features/assistant/AssistantDrawerProvider.jsx';
import { useAssistantProvider } from '../features/settings/hooks/useAssistantProvider.js';
import { deriveAssistantContext } from '../features/assistant/useAssistantContext.js';
import { buildAssistantSessionPayload } from '../features/assistant/assistantAppBridge.js';
import {
  useGradeFormulaBootSyncEffect, useEvaluateBounceEffect,
  useInitialLandingEffect, useProjectScrollResetEffect, useVisibleStandardsHydrationEffect,
} from './useAppEffects.js';
import { buildBreadcrumbSiblingsFor } from '../features/side-pane/breadcrumbSiblings.js';

// App.jsx's hook groups, extracted verbatim to keep App() itself under the
// function-length cap without touching hook call order: each group below is
// called unconditionally, once, in the same relative position App() used to
// call its member hooks inline -- React only cares about that sequence, not
// how many function frames it's nested inside.

export function computeIsEvaluating(state) {
  // While an evaluation is running we block any path that would open the
  // onboarding wizard or start a second evaluation — only one job may be in
  // flight at a time.
  return state.evalLifecycle?.job?.status === 'running';
}

// Warm the Overview's lazy chunks (DashboardPage + the recharts chart) while
// the startup loader is up — see bootChunks.js for why page-mount time
// measured too late. Also owns the passive shared-repo content signal (the
// wizard auto-open, one-shot landing redirect, and "browse remote
// repositories" empty-state actions share this — same react-query cache as
// ProjectsPage/Settings, no extra fetching) and the two pieces of App-local
// UI state that don't depend on anything else.
export function useAppBootExtras() {
  useEffect(() => { warmOverviewChunks(); }, []);
  const sharedSignal = useSharedContentSignal();
  const [sidebarPinned, setSidebarPinned] = useState(false);
  // Incremented after every successful dismiss POST so the violations
  // page's dismissed sub-tab knows to refetch its list. Without this, a
  // dismiss made on the principle / file detail page never appeared in the
  // dismissed list until the user switched projects — the list was only
  // fetched once on mount.
  const [dismissRefreshKey, setDismissRefreshKey] = useState(0);
  const bumpDismissRefresh = () => setDismissRefreshKey((k) => k + 1);
  return { sharedSignal, sidebarPinned, setSidebarPinned, dismissRefreshKey, bumpDismissRefresh };
}

// Live assistant context: the pure derivation reuses the app-state object
// we already hold (calling useAssistantContext() would spin up a second
// useAppState and duplicate every dashboard query). The gate provides the
// active assistant provider/model. Starts (or re-starts) the assistant
// session when the drawer is open and on any provider/model/project/run
// change while it stays open. startSession dedupes by context key, so
// re-runs with an unchanged context no-op; a real project/run switch
// produces a fresh session. We deliberately do NOT start a session while the
// drawer is closed — sends only originate from the open drawer, so
// first-open is early enough and avoids needless sessions. Shared projects
// get READ-ONLY sessions: the backend roots their reads in the shared clone
// and registers no mutating tools, so the drawer no longer closes on a
// source switch; the source-keyed session context re-keys instead.
export function useAppAssistant(state) {
  const { showToast } = useSidePane();
  const assistantGate = useAssistantProvider();
  const assistantCtx = deriveAssistantContext(state, assistantGate);
  const { isOpen: assistantOpen, activeTab: drawerTab, startSession: startAssistantSession } = useAssistantDrawer();
  const { provider: asstProvider, model: asstModel, projectId: asstProjectId, runId: asstRunId, source: asstSource } = assistantCtx;
  useEffect(() => {
    if (!assistantOpen || drawerTab !== 'assistant') return;
    startAssistantSession(buildAssistantSessionPayload({
      provider: asstProvider, model: asstModel, projectId: asstProjectId, runId: asstRunId, source: asstSource,
    }));
  }, [assistantOpen, drawerTab, asstProvider, asstModel, asstProjectId, asstRunId, asstSource, startAssistantSession]);
  return { showToast, assistantCtx };
}

// Grade-formula boot sync, wizard entry/auto-open lifecycle, and the
// Evaluate-tab bounce guard — see useAppEffects.js and
// features/onboarding/useWizardLifecycle.js for the individual rationales.
export function useAppWizardBounce({ state, selectedProjectInfo, isEvaluating, sharedSignal }) {
  useGradeFormulaBootSyncEffect();
  const { wizardEntry, setWizardEntry, wizardHandlers } = useWizardLifecycle({
    state, navTab: state.navTab, isEvaluating, sharedSignal,
  });
  const hasCurrentProjectRuns = (selectedProjectInfo?.runsCount ?? 0) > 0;
  useEvaluateBounceEffect({ state, selectedProjectInfo, hasCurrentProjectRuns });
  return { wizardEntry, setWizardEntry, wizardHandlers, hasCurrentProjectRuns };
}

// Startup-loader gating, the one-shot initial-landing redirect, the native
// macOS Help-menu nav bridge, and the two selected-project-keyed sync
// effects (scroll reset, visible-standards hydration).
export function useAppNavBoot({ state, activeTab, navTab, sharedSignal }) {
  // NOT memoized on purpose: a per-render read is what makes this pick up a
  // Settings change (active provider/model) without its own change listener.
  const sidebarProvider = readActiveProviderSelection();
  const sidebarModel = readActiveProviderModel(sidebarProvider);
  const showStartupLoader = useStartupLoader({
    projectsLoaded: state.projectsLoaded,
    projectsLoadFailed: state.projectsLoadFailed,
    projectsCount: state.projects.length,
    selectedProject: state.selectedProject,
    selectedSource: state.selectedSource,
    activeTab,
    dashboard: state.dashboard,
    accumulated: state.accumulated,
    error: state.error,
    loading: state.loading,
  });
  useInitialLandingEffect({ state, sharedSignal, activeTab, navTab });
  useNativeNavBridge(navTab);
  useProjectScrollResetEffect(state.selectedProject);
  useVisibleStandardsHydrationEffect(state.selectedProject);
  return { sidebarProvider, sidebarModel, showStartupLoader };
}

// Day-label memo, dark/light theme sync, visible-standards-filtered
// trend/accumulated data, and the breadcrumb jump-bar's sibling lookup.
export function useAppDerived({ state, navTab, navSwapAt, activePage }) {
  const currentDayLabel = useMemo(
    () => formatDayLabel(state.dashboard?.trend, state.currentOverviewRun, state.dailyRuns, state.overviewRunIndex),
    [state.dashboard?.trend, state.currentOverviewRun, state.dailyRuns, state.overviewRunIndex]
  );
  // Resolve whether the UI is currently rendering dark and keep the native
  // titlebar in sync; the toggle is used by the topbar's moon/sun button so
  // the icon reflects what's on-screen, not just the saved mode preference.
  const { effectiveDark, toggleTheme } = useStartupTheme(state.settings);
  // Sidebar counts should respect the user's currently-visible standards so
  // they match the numbers shown on the Violations and History pages.
  const visibleSet = useMemo(() => new Set(readVisibleStandardIds()), []);
  const filteredTrend = useMemo(
    () => filterTrendByVisibleStandards(state.dashboard?.trend || [], visibleSet),
    [state.dashboard?.trend, visibleSet]
  );
  const filteredAccumulated = useMemo(
    () => filterAccumulatedByVisibleStandards(state.accumulated, visibleSet, filteredTrend, null),
    [state.accumulated, visibleSet, filteredTrend]
  );
  const breadcrumbSiblingsFor = useCallback(
    buildBreadcrumbSiblingsFor({
      selectedProject: state.selectedProject, navTab, navSwapAt, activePage, filteredAccumulated,
    }),
    [state.selectedProject, navTab, navSwapAt, activePage, filteredAccumulated]
  );
  return { currentDayLabel, effectiveDark, toggleTheme, filteredTrend, filteredAccumulated, breadcrumbSiblingsFor };
}

// Live run progress for the topbar chrome (run chip + bottom hairline).
// Shares the JobStatStrip/ScanProgress query cache entry, so this adds no
// extra polling.
export function useAppEvalProgress({ state, isEvaluating }) {
  const evalJob = state.evalLifecycle?.job;
  const { data: evalProgress } = useEvaluationProgress(isEvaluating ? evalJob?.jobId : undefined, !isEvaluating);
  return useMemo(() => {
    if (!isEvaluating) return null;
    const overall = computeOverallProgress(evalProgress);
    const runningDim = (evalProgress?.dimensions || []).find((d) => d?.state === 'running');
    return {
      dimension: runningDim?.id ? String(runningDim.id).toLowerCase() : null,
      percent: overall.totalFiles > 0 ? overall.overallPct : null,
    };
  }, [isEvaluating, evalProgress]);
}
