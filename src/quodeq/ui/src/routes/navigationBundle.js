import { t } from '../strings/index.js';

/**
 * Build the `navigation` prop bundle ROUTE_RENDERERS consume. Every
 * navigation key a route renderer reads MUST be forwarded here -- a route
 * consuming a key the bundle lacks fails silently at click time (the
 * handler throws mid-event and the UI just doesn't respond; that's how the
 * repositories local/online tab flip broke when handleNavigateReplace was
 * consumed but never forwarded). Exported so producer and consumer can be
 * pinned together in tests without mounting the whole App.
 *
 * Moved out of routes/renderers.jsx verbatim (move-only refactor); the
 * inline onAddProject/onImportProject/onTakeTour/onResumeSetup callbacks
 * became the named `make*` factories below for readability -- same logic,
 * same closures.
 */

function makeOnAddProject({ isEvaluating, showToast, setWizardEntry, projects }) {
  return () => {
    if (isEvaluating) {
      showToast(t('evaluate.busyAddProject'));
      return;
    }
    setWizardEntry({ startStep: 'repo-scan', isFirstProject: projects.length === 0 });
  };
}

function makeOnImportProject({ isEvaluating, showToast, handleImportProject }) {
  return () => {
    if (isEvaluating) {
      showToast(t('evaluate.busyImportProject'));
      return;
    }
    handleImportProject();
  };
}

function makeOnTakeTour({ isEvaluating, showToast, setWizardEntry }) {
  return () => {
    if (isEvaluating) {
      showToast(t('evaluate.busyStartTour'));
      return;
    }
    setWizardEntry({ startStep: 'welcome', isFirstProject: true });
  };
}

function makeOnResumeSetup({ isEvaluating, showToast, setWizardEntry }) {
  return (projectId) => {
    if (isEvaluating) {
      showToast(t('evaluate.busyResumeSetup'));
      return;
    }
    setWizardEntry({
      startStep: 'provider',
      isFirstProject: false,
      presetProjectId: projectId,
    });
  };
}

export function buildNavigationBundle({ state, navTab, navStackLength, isEvaluating, showToast, setWizardEntry, sharedHasContent = false }) {
  return {
    selectedProject: state.selectedProject, selectedSource: state.selectedSource, selectedRun: state.selectedRun, projects: state.projects,
    projectsLoaded: state.projectsLoaded,
    projectsLoadFailed: state.projectsLoadFailed,
    retryLoadProjects: state.retryLoadProjects,
    warmup: state.warmup,
    loadProjects: state.loadProjects,
    handleNavigate: state.handleNavigate, handleNavigateReplace: state.handleNavigateReplace, navPop: state.navPop, handleRunSelect: state.handleRunSelect,
    // navStack + navGoTo let a route unwind history to an earlier entry of
    // its own page (the map's drill-up) instead of pushing a duplicate.
    navStack: state.navStack, navGoTo: state.navGoTo,
    handleProjectChange: state.handleProjectChange, navTab, navStackLength,
    handleDeleteProject: state.handleDeleteProject, handleExportProject: state.handleExportProject, handleRelocateProject: state.handleRelocateProject, handleImportProject: state.handleImportProject,
    historySelectedRun: state.historySelectedRun, setHistorySelectedRun: state.setHistorySelectedRun,
    currentOverviewRun: state.currentOverviewRun, handleRunPrev: state.handleRunPrev, handleRunNext: state.handleRunNext, handleRunLatest: state.handleRunLatest,
    prefetchHandlers: state.prefetchHandlers,
    onAddProject: makeOnAddProject({ isEvaluating, showToast, setWizardEntry, projects: state.projects }),
    onImportProject: makeOnImportProject({ isEvaluating, showToast, handleImportProject: state.handleImportProject }),
    onTakeTour: makeOnTakeTour({ isEvaluating, showToast, setWizardEntry }),
    onResumeSetup: makeOnResumeSetup({ isEvaluating, showToast, setWizardEntry }),
    // null when the shared repo has no content — consumers use the nullness
    // to hide their "browse remote repositories" affordance.
    onBrowseRemote: sharedHasContent ? () => navTab('projects') : null,
    isEvaluating,
  };
}
