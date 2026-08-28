/**
 * Route renderers: the per-route view composition App.jsx's MainContent
 * dispatches to, plus the prop-bundle builders the renderers consume.
 * Moved out of App.jsx verbatim (move-only refactor); App state arrives via
 * the explicit `props` bundles — no context. Everything here is exported so
 * the route contracts stay unit-testable without mounting the whole App
 * (which needs ~8 providers).
 */
import { lazy } from 'react';
import EmptyState from '../components/EmptyState.jsx';
import EmptyStateWithTour from '../features/onboarding/components/EmptyStateWithTour.jsx';
import { dismissWithReconcile } from '../features/findings/dismissFlow.js';
import { buildProjectRootFile } from '../utils/explorerUtils.js';
import { t } from '../strings/index.js';

const DashboardPage = lazy(() => import('../features/dashboard/components/DashboardPage.jsx'));
const ExplorerPage = lazy(() => import('../features/explorer/components/ExplorerPage.jsx'));
const FileDetailPage = lazy(() => import('../features/explorer/components/FileDetailPage.jsx'));
const PrincipleDetailPage = lazy(() => import('../features/explorer/components/PrincipleDetailPage.jsx'));
const FindingDetailPage = lazy(() => import('../features/explorer/components/FindingDetailPage.jsx'));
const ProjectsPage = lazy(() => import('../features/dashboard/components/ProjectsPage.jsx'));
const HistoryPage = lazy(() => import('../features/history/components/HistoryPage.jsx'));
const EvaluateScreen = lazy(() => import('../features/evaluation/components/EvaluateScreen.jsx'));
const SettingsPage = lazy(() => import('../features/settings/components/SettingsPage.jsx'));
const GradeFormulaPage = lazy(() => import('../features/grade-formula/GradeFormulaPage.jsx'));
const StandardsPage = lazy(() => import('../features/standards/StandardsPage.jsx'));
const ViolationsPage = lazy(() => import('../features/violations/components/ViolationsPage.jsx'));
const MapPage = lazy(() => import('../features/map/components/MapPage.jsx'));
const HelpPage = lazy(() => import('../features/help/components/HelpPage.jsx'));
const ComparePage = lazy(() => import('../features/compare/components/ComparePage.jsx'));

// Tabs that are reachable with zero projects. `projects` is in here so a
// fresh-install user can land on Projects and add their first one without
// hitting the "no analyzed projects yet" wall.
const NO_PROJECT_TABS = ['projects', 'evaluate', 'standards', 'settings', 'help', 'grade-formula', 'compare'];
const SELF_HANDLED_EMPTY = new Set(['overview', 'map', 'violations', 'history']);

// Shared projects have no mutation route on the backend (dismiss is
// local-only by design, and the same project id can exist in both local and
// shared worlds by design — a dismiss POST for a shared project's id would
// otherwise silently corrupt the LOCAL project's cache with shared-derived
// deltas). Every route renderer below that injects onDismiss calls this
// first: pass `undefined` for shared so the leaf components (EvalCards'
// EvalViolationCard, FileDetailPage's ViolationCard) self-hide the dismiss
// button rather than wiring up a handler that must never fire.
export function isSharedSource(selectedSource) {
  return selectedSource === 'shared';
}

/**
 * @param {{ serverHealth: Object, evaluation: Object, selectedProject: string, projects: Array, onGoToProjects: Function, onGoToSettings: Function, preselectDims: string[]|undefined }} props
 * @returns {JSX.Element}
 */
function EvaluateCase({ evaluation, selectedProject, projects, onGoToProjects, onGoToSettings, preselectDims }) {
  const { job, jobError, liveViolations, handleStartEvaluation, handleEvalDismiss, cancelEvaluation, startedProject } = evaluation;
  const projectInfo = projects?.find(p => (p.id || p.name) === selectedProject) || null;
  // The in-progress card describes the running job's own project, which can
  // differ from the UI's global selection. Resolve it the same way so the
  // card label follows the job rather than the selection. Before the
  // report-path marker resolves outputProject, the project the job was
  // started for fills the gap; the global selection is never used.
  const jobProjectInfo = job?.outputProject
    ? (projects?.find(p => (p.id || p.name) === job.outputProject) || null)
    : null;
  const startedProjectInfo = startedProject
    ? (projects?.find(p => (p.id || p.name) === startedProject) || null)
    : null;
  return (
    <>
      <EvaluateScreen
        evaluation={{ job, jobError, liveViolations }}
        context={{ selectedProject, projectInfo, jobProjectInfo, startedProjectInfo, preselectDims }}
        actions={{ onStart: handleStartEvaluation, onDismiss: handleEvalDismiss, onCancel: cancelEvaluation, onGoToProjects, onGoToSettings }}
      />
    </>
  );
}

/**
 * @param {{ settings: Object }} props
 * @returns {JSX.Element}
 */
function SettingsCase({ settings, onOpenGradeFormula, onSharedDisconnected }) {
  return (
    <SettingsPage
      theme={{ mode: settings.themeMode, family: settings.themeFamily, onApplyMode: settings.applyMode, onApplyFamily: settings.applyFamily }}
      onOpenGradeFormula={onOpenGradeFormula}
      onSharedDisconnected={onSharedDisconnected}
    />
  );
}

function resolveHistorySelectedRunId(selectedRun, trend) {
  if (selectedRun && selectedRun !== 'latest' && trend.some((t) => t.runId === selectedRun)) return selectedRun;
  return trend.length > 0 ? trend[0].runId : null;
}

/**
 * Build the `navigation` prop bundle ROUTE_RENDERERS consume. Every
 * navigation key a route renderer reads MUST be forwarded here -- a route
 * consuming a key the bundle lacks fails silently at click time (the
 * handler throws mid-event and the UI just doesn't respond; that's how the
 * repositories local/online tab flip broke when handleNavigateReplace was
 * consumed but never forwarded). Exported so producer and consumer can be
 * pinned together in tests without mounting the whole App.
 */
/**
 * The dashboard data bundle handed to every DashboardPage route.
 *
 * Same hazard as buildNavigationBundle, quieter failure: this is an explicit
 * key whitelist, so a field added to useAppState and read by DashboardPage
 * silently arrives as undefined unless it is forwarded here. Nothing throws --
 * the feature just never activates (that is how scoresPending, and the
 * dimension-panel pending state that depends on it, was inert at first).
 * Exported so producer and consumer can be pinned together in tests.
 */
export function buildDashboardDataBundle({ state, sharedHasContent = false }) {
  return {
    selectedProject: state.selectedProject, selectedSource: state.selectedSource, selectedRun: state.selectedRun, projects: state.projects,
    projectsLoaded: state.projectsLoaded,
    projectsLoadFailed: state.projectsLoadFailed,
    onProjectsRetry: state.retryLoadProjects,
    warmup: state.warmup,
    dashboard: state.dashboard, accumulated: state.accumulated, latestAccumulated: state.latestAccumulated, loading: state.loading, isFetching: state.isFetching, error: state.error,
    onRetry: state.refreshDashboardActive,
    scoresPending: state.scoresPending,
    sharedProjectInfo: state.sharedProjectInfo,
    availableRuns: state.availableRuns, dailyRuns: state.dailyRuns, overviewRunIndex: state.overviewRunIndex,
    selectedDisplayName: state.selectedDisplayName,
    granularity: state.granularity, onGranularityChange: state.onGranularityChange,
    sharedHasContent,
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
    onAddProject: () => {
      if (isEvaluating) {
        showToast(t('evaluate.busyAddProject'));
        return;
      }
      setWizardEntry({ startStep: 'repo-scan', isFirstProject: state.projects.length === 0 });
    },
    onImportProject: () => {
      if (isEvaluating) {
        showToast(t('evaluate.busyImportProject'));
        return;
      }
      state.handleImportProject();
    },
    onTakeTour: () => {
      if (isEvaluating) {
        showToast(t('evaluate.busyStartTour'));
        return;
      }
      setWizardEntry({ startStep: 'welcome', isFirstProject: true });
    },
    onResumeSetup: (projectId) => {
      if (isEvaluating) {
        showToast(t('evaluate.busyResumeSetup'));
        return;
      }
      setWizardEntry({
        startStep: 'provider',
        isFirstProject: false,
        presetProjectId: projectId,
      });
    },
    // null when the shared repo has no content — consumers use the nullness
    // to hide their "browse remote repositories" affordance.
    onBrowseRemote: sharedHasContent ? () => navTab('projects') : null,
    isEvaluating,
  };
}

/**
 * After the shared repository is disconnected in Settings, a currently
 * 'shared' selection is left pointing at a project that no longer resolves
 * anywhere in the app (its source has no config left) -- the user would be
 * stranded on a broken view. Resolve what handleProjectChange should be
 * called with to recover: the first local project if one exists, otherwise
 * the app's own "no project selected" state (empty id, 'local' source, same
 * as a fresh install / readStoredProject's default -- see useProjectState.js).
 * Returns null when there's nothing to do (selection wasn't 'shared').
 * Exported so the recovery contract is unit-testable without mounting the
 * whole App.
 */
export function resolveSelectionAfterSharedDisconnect({ selectedSource, projects }) {
  if (selectedSource !== 'shared') return null;
  const first = (projects || [])[0];
  const id = first ? (first.id || first.name || first) : '';
  return { id, source: 'local' };
}

function renderEvalPrincipleDetail(params, props) {
  const { selectedProject, selectedRun, selectedSource } = props.navigation;
  const evalPrincipal = {
    ...params.evalPrincipal,
    project: params.evalPrincipal?.project || selectedProject || '',
    runId: params.evalPrincipal?.runId || selectedRun || '',
  };
  return (
    <PrincipleDetailPage
      evalPrincipal={evalPrincipal}
      severityFilter={params.severity || null}
      // The rescored payload from the dismiss POST is applied by
      // PrincipleDetailPage to its local liveScore/liveGrade; the shared
      // dismissWithReconcile tail covers the accumulated (cross-run) rollup.
      // The evalPrincipal's own project, NOT the global selection: a
      // cross-project entry (Compare's principle jump, a parent dimension's
      // fromProject) must dismiss into the project the finding belongs to.
      onDismiss={isSharedSource(selectedSource) ? undefined : (v) => dismissWithReconcile({
        violation: v,
        fallbackDimension: evalPrincipal.dimension,
        runId: evalPrincipal.runId,
        explicitProject: evalPrincipal.project,
        selectedProject,
        deps: props,
      })}
    />
  );
}

// Exported so unit tests can pin the runId-threading contract without having
// to mount the whole App. Callers from the Violations page must pass the
// dimension's ``fromRunId`` — see ``ViolationsRoute.navigateToPrinciple`` for
// the regression history.
export function buildEvalPrincipal(principleObj, principleGrade, runId) {
  const violations = principleObj.violations || [];
  const compliance = principleObj.compliance || [];
  return {
    principle: principleObj.principle,
    score: principleGrade?.score || null,
    grade: principleGrade?.grade || null,
    dimension: principleObj.dimension || '',
    runId: runId || '',
    principleData: {
      name: principleObj.principle,
      grade: principleGrade?.grade || null,
      violations,
      compliance,
    },
    dimViolations: violations,
    dimCompliance: compliance,
  };
}

function ViolationsRoute({ params, props }) {
  const acc = props.dashboardData.latestAccumulated || props.dashboardData.accumulated;
  const dims = acc?.dimensions || [];
  const nav = props.navigation.handleNavigate;

  const dimMap = new Map(dims.map(d => [d.dimension, d]));
  const principleMap = new Map(
    dims.flatMap(d => (d.principles || []).map(p => [`${d.dimension}\0${p.name || p.principle}`, p]))
  );
  function navigateToPrinciple(principleObj, severity) {
    const dim = dimMap.get(principleObj.dimension);
    const pg = principleMap.get(`${principleObj.dimension}\0${principleObj.principle}`);
    // dim.fromRunId is the run whose data populated this accumulated entry;
    // threading it through lets the dismiss POST carry a real run id so the
    // backend can rescore and project the action into SQL — without this the
    // PrincipleDetail score never moves on dismiss and the entry never lands
    // on the Dismissed tab.
    nav('evalprinciple', {
      evalPrincipal: buildEvalPrincipal(principleObj, pg, dim?.fromRunId),
      severity,
      sourceTab: 'violations',
    });
  }

  function navigateToDimension(row, severity) {
    const dim = row.raw || dimMap.get(row.dimension);
    if (!dim) return;
    // Cell clicks on a dimension row (numeric severity columns or the
    // "violations" total) drill into the dimension's findings — match the
    // project/run pattern by handing FileDetailPage a synthetic file
    // aggregated from the dimension, with the chosen severity preselected.
    const dimFile = buildProjectRootFile([dim], dim.dimension);
    const severityFilter = severity || 'all';
    nav('file', {
      file: dimFile,
      severityFilter,
      runId: dim.fromRunId,
      dateLabel: dim.fromDateLabel,
      sourceTab: 'violations',
    });
  }

  return (
    <ViolationsPage
      data={{
        accumulated: acc,
        accumulatedDimensions: dims,
        selectedProject: props.navigation.selectedProject,
        selectedSource: props.navigation.selectedSource,
        projects: props.navigation.projects,
        projectsLoaded: props.navigation.projectsLoaded,
        projectName: props.dashboardData.selectedDisplayName,
        loading: props.dashboardData.loading,
        isFetching: props.dashboardData.isFetching,
        error: props.dashboardData.error,
        dismissRefreshKey: props.dismissRefreshKey,
      }}
      callbacks={{
        onDimensionClick: (dim) => nav('explorer', { dimension: dim.dimension, runId: dim.fromRunId, dateLabel: dim.fromDateLabel, fromProject: dim.fromProject, sourceTab: 'violations' }),
        onFileClick: (fileObj, opts) => nav('file', { file: fileObj, sourceTab: 'violations', severityFilter: opts?.severity || null }),
        onCellClick: ({ row, severity }) => {
          if (row.type === 'principle' && row.principleObj) {
            navigateToPrinciple(row.principleObj, severity);
          } else {
            navigateToDimension(row, severity);
          }
        },
        onPrincipleClick: (principleObj) => navigateToPrinciple(principleObj),
        // ViolationsPage fires onRefresh on EVERY mount (its tabKey effect),
        // including plain drill-down/back navigation with no mutation --
        // the page remounts on every round trip. onRefresh must stay wired
        // to the lazy refreshDashboard (mark-stale, refetchType:'none') so
        // plain navigation never forces an active refetch of the 10-20 MB
        // dashboard payload. Restore/delete (single + bulk) route through a
        // SEPARATE onReconcile callback via useDismissedFindings, called
        // alongside onRefresh from its four mutation handlers.
        // restore-all/delete-all return a payload applyMutationDelta can't
        // patch (scores:null, delta.isLatest:false), so those need the
        // debounced ACTIVE reconcile — see scheduleDashboardReconcile in
        // useDashboard.js.
        onRefresh: props.refreshDashboard,
        onReconcile: props.scheduleDashboardReconcile,
        onNavigate: nav,
        onRetry: props.dashboardData.onRetry,
      }}
      isDirectNav={props.navigation.navStackLength === 1}
      tabKey={params._tabKey || 0}
      // The by-dimension / by-file / dismissed flip is view state on the SAME
      // screen: it lives in the route entry so back/forward and the crumb see
      // it, but flipping replaces (never pushes) so history doesn't grow.
      // Params are spread forward so _tabKey survives the flip.
      subTab={params.subTab || 'dimension'}
      onSubTabChange={(v) => props.navigation.handleNavigateReplace('violations', { ...params, subTab: v })}
    />
  );
}

// Exported for the same reason as buildEvalPrincipal — a unit-testable pin
// on the per-route onDismiss source-gating contract without mounting the
// whole App (which needs ~8 providers). Calling e.g.
// ROUTE_RENDERERS.file(params, props) just builds the React element tree; it
// doesn't render, so the returned element's props can be asserted on directly.
export const ROUTE_RENDERERS = {
  overview: (params, props) => <DashboardPage data={props.dashboardData} callbacks={{ onNavigate: props.navigation.handleNavigate, onRunSelect: props.navigation.handleRunSelect, onProjectsReload: props.navigation.loadProjects, onRetry: props.dashboardData.onRetry, onProjectsRetry: props.dashboardData.onProjectsRetry }} runMode={false} />,
  violations: (params, props) => <ViolationsRoute params={params} props={props} />,
  map: (params, props) => {
    const acc = props.dashboardData.latestAccumulated || props.dashboardData.accumulated;
    const isDirectNav = props.navigation.navStackLength === 1;
    // The viz drill-down is a real nav-stack entry: drilling into a folder
    // pushes (browser back climbs back out), and navigating up to a path
    // that already sits in the trailing run of map entries unwinds history
    // to it instead of stacking a duplicate. Mode/style toggles replace in
    // place so flipping them never grows history. Params are spread forward
    // on every hop so _tabKey (the fresh-tab-click reset signal) survives.
    const handlePathChange = (path) => {
      const current = params.path || '';
      if (path === current) return;
      const stack = props.navigation.navStack || [];
      for (let i = stack.length - 2; i >= 0 && stack[i].page === 'map'; i--) {
        if ((stack[i].path || '') === path) {
          props.navigation.navGoTo(i);
          return;
        }
      }
      props.navigation.handleNavigate('map', { ...params, path });
    };
    const replaceView = (patch) => props.navigation.handleNavigateReplace('map', { ...params, ...patch });
    return <MapPage
      data={{
        accumulated: acc,
        dashboard: props.dashboardData.dashboard,
        projectName: props.dashboardData.selectedDisplayName,
        projects: props.navigation.projects,
        projectsLoaded: props.navigation.projectsLoaded,
        selectedProject: props.navigation.selectedProject,
        selectedSource: props.navigation.selectedSource,
        loading: props.dashboardData.loading,
        isFetching: props.dashboardData.isFetching,
        error: props.dashboardData.error,
      }}
      callbacks={{ onNavigate: props.navigation.handleNavigate, onRefresh: props.refreshDashboard, onRetry: props.dashboardData.onRetry }}
      nav={{
        path: params.path || '',
        vizStyle: params.vizStyle,
        viewMode: params.viewMode,
        galaxyMode: params.galaxyMode,
        onPathChange: handlePathChange,
        onVizStyleChange: (v) => replaceView({ vizStyle: v }),
        onViewModeChange: (v) => replaceView({ viewMode: v }),
        onGalaxyModeChange: (v) => replaceView({ galaxyMode: v }),
      }}
      isDirectNav={isDirectNav}
      tabKey={params._tabKey || 0}
    />;
  },
  run: (params, props) => <DashboardPage data={props.dashboardData} callbacks={{ onNavigate: props.navigation.handleNavigate, onRetry: props.dashboardData.onRetry, onProjectsRetry: props.dashboardData.onProjectsRetry }} runMode={true} />,
  history: (params, props) => {
    const trend = props.dashboardData.dashboard?.trend || [];
    const runs = props.dashboardData.availableRuns || [];
    const idx = props.dashboardData.overviewRunIndex || 0;
    return (
      <HistoryPage
        trend={trend}
        selection={{
          selectedRunId: resolveHistorySelectedRunId(props.navigation.historySelectedRun, trend),
          selectedRunScore: props.dashboardData.accumulated?.summary?.numericAverage,
        }}
        availableRuns={runs}
        dimensions={{
          accumulatedDimensions: props.dashboardData.accumulated?.dimensions || [],
          lastRun: { date: props.dashboardData.accumulated?.dimensions?.[0]?.fromDateLabel, runId: props.dashboardData.accumulated?.dimensions?.[0]?.fromRunId },
        }}
        callbacks={{
          onRunClick: (runId, dateLabel) => props.navigation.handleNavigate('history-run', { runId, dateLabel }),
          onDimensionClick: (dim) => props.navigation.handleNavigate('explorer', { dimension: dim.dimension, runId: dim.fromRunId, dateLabel: dim.fromDateLabel, fromProject: dim.fromProject }),
          onNavigate: props.navigation.handleNavigate,
          onRunChange: props.navigation.setHistorySelectedRun,
          // Run deletion changes the accumulated rollup the Overview grade is
          // built from — same mutation class as dismiss/restore, so it gets
          // the same debounced ACTIVE reconcile (mark-stale alone never
          // reaches the always-mounted Overview observer).
          onRunDeleted: () => props.scheduleDashboardReconcile?.(),
        }}
        projects={props.navigation.projects}
        projectsLoaded={props.navigation.projectsLoaded}
        selectedProject={props.navigation.selectedProject}
        selectedSource={props.navigation.selectedSource}
        loading={props.dashboardData.loading}
        isFetching={props.dashboardData.isFetching}
        error={props.dashboardData.error}
        onRetry={props.dashboardData.onRetry}
        projectInfo={props.navigation.projects?.find((p) => (p.id || p.name) === props.navigation.selectedProject) || null}
      />
    );
  },
  'history-run': (params, props) => <DashboardPage data={props.dashboardData} callbacks={{ onNavigate: props.navigation.handleNavigate, onRetry: props.dashboardData.onRetry }} runMode={true} />,
  explorer: (params, props) => (
    <ExplorerPage
      project={params.fromProject || props.navigation.selectedProject}
      dimension={params.dimension}
      runId={params.runId}
      dateLabel={params.dateLabel}
      sourceTab={params.sourceTab}
      selectedSource={params.fromSource || props.navigation.selectedSource}
      onNavigate={props.navigation.handleNavigate}
      refreshSignal={props.dashboardData.dashboard}
      trend={props.dashboardData.dashboard?.trend || []}
      granularity={props.dashboardData.granularity}
      onGranularityChange={props.dashboardData.onGranularityChange}
    />
  ),
  evaluate: (params, props) => {
    // Shared projects have no Evaluate flow (evaluation is local-only) --
    // shouldShowEvaluateButton already keeps the TopBar's Evaluate button
    // from ever linking here for a shared selection, but a stale nav-stack
    // entry (e.g. the user was sitting on Evaluate and switched to a shared
    // project) could still land the router on this route. Belt-and-braces:
    // fall back to the Overview, the least-surprising landing spot, rather
    // than rendering a dead-end evaluate screen with no source-appropriate
    // action.
    if (isSharedSource(props.navigation.selectedSource)) {
      return ROUTE_RENDERERS.overview(params, props);
    }
    return <EvaluateCase evaluation={props.evaluation} selectedProject={props.navigation.selectedProject} projects={props.navigation.projects} preselectDims={params.preselectDims} onGoToProjects={() => props.navigation.navTab('projects')} onGoToSettings={() => props.navigation.navTab('settings')} />;
  },
  file: (params, props) => (
    <FileDetailPage
      file={params.file}
      runId={params.runId}
      dateLabel={params.dateLabel}
      severityFilter={params.severityFilter || params.severity || null}
      // The entry's own project, not the global selection: a file opened
      // from a cross-project explorer (fromProject) must dismiss into the
      // project the finding belongs to. Same identity rule as the
      // evalprinciple route — encoded once, in dismissWithReconcile.
      onDismiss={isSharedSource(props.navigation.selectedSource) ? undefined : (v) => dismissWithReconcile({
        violation: v,
        runId: params.runId,
        explicitProject: params.fromProject,
        selectedProject: props.navigation.selectedProject,
        deps: props,
      })}
    />
  ),
  evalprinciple: renderEvalPrincipleDetail,
  'eval-principle-detail': renderEvalPrincipleDetail,
  finding: (params, props) => (
    <FindingDetailPage
      finding={params.finding}
      principle={params.principle}
      dimension={params.dimension}
      // Same identity rule as the file and evalprinciple routes.
      onDismiss={isSharedSource(props.navigation.selectedSource) ? undefined : (v) => dismissWithReconcile({
        violation: v,
        fallbackDimension: params.dimension,
        runId: params.runId,
        explicitProject: params.fromProject,
        selectedProject: props.navigation.selectedProject,
        deps: props,
      })}
    />
  ),
  settings: (params, props) => <SettingsCase
    settings={props.settings}
    onOpenGradeFormula={() => props.navigation.handleNavigate('grade-formula')}
    onSharedDisconnected={() => {
      const next = resolveSelectionAfterSharedDisconnect({
        selectedSource: props.navigation.selectedSource,
        projects: props.navigation.projects,
      });
      if (next) props.navigation.handleProjectChange(next.id, next.source);
    }}
  />,
  'grade-formula': (params, props) => <GradeFormulaPage navigation={props.navigation} />,
  projects: (params, props) => <ProjectsPage projects={props.navigation.projects} projectsLoaded={props.navigation.projectsLoaded} selectedProject={props.navigation.selectedProject} isEvaluating={props.navigation.isEvaluating} filters={params.filters} actions={{ onSelect: (id, source) => { props.navigation.handleProjectChange(id, source); props.navigation.navTab('overview'); }, onDelete: props.navigation.handleDeleteProject, onExport: props.navigation.handleExportProject, onRelocate: props.navigation.handleRelocateProject, onAddProject: props.navigation.onAddProject, onImportProject: props.navigation.onImportProject, onResumeSetup: props.navigation.onResumeSetup, onFiltersChange: (filters) => props.navigation.handleNavigateReplace('projects', { filters }), onProjectsReload: props.navigation.loadProjects }} />,
  standards: (params, props) => <StandardsPage onRescan={(dims) => props.navigation.navTab('evaluate', { preselectDims: dims })} />,
  help: () => <HelpPage />,
  compare: (params, props) => (
    <ComparePage
      projects={props.navigation.projects}
      projectsLoaded={props.navigation.projectsLoaded}
      dimension={params.dimension || null}
      onOpenProject={(id, source = 'local') => {
        // Remote fleet rows open through the shared source; the same
        // machinery the projects drawer uses for shared selections.
        props.navigation.handleProjectChange(id, source);
        props.navigation.navTab('overview');
      }}
      // Drill-down is a real nav-stack entry: push from the fleet so the
      // browser back button returns there; replace when switching between
      // dimensions so tab-hopping doesn't grow history.
      onOpenDimension={(key) => props.navigation.handleNavigate('compare', { dimension: key })}
      onSwitchDimension={(key) => props.navigation.handleNavigateReplace('compare', { dimension: key })}
      // Cross-project principle jump: the evalPrincipal carries its own
      // project, so the selection doesn't change and back pops to Compare.
      onOpenEvalPrincipal={(evalPrincipal) => props.navigation.handleNavigate('evalprinciple', { evalPrincipal, sourceTab: 'compare' })}
      // Standings row -> that project's own screen of the SAME dimension
      // (the explorer's cross-project fromProject entry), pushed for the
      // same back-pops-to-Compare contract.
      onOpenProjectDimension={(target) => props.navigation.handleNavigate('explorer', {
        dimension: target.dimName,
        runId: target.runId,
        dateLabel: target.dateLabel,
        fromProject: target.id,
        // The entry's own source, like its own project: the explorer must
        // read a local fromProject from the local API even while the
        // global selection sits on the shared source (and vice versa).
        fromSource: target.source || 'local',
        sourceTab: 'compare',
      })}
      // Head-to-head is a push like the dimension drill-down: back returns
      // to the fleet with the two-project scope still selected.
      duel={params.duel || null}
      onOpenDuel={(ids) => props.navigation.handleNavigate('compare', { duel: ids })}
      onBack={props.navigation.navPop}
    />
  ),
};

// The app-level "no local projects" wall in MainContent. Route pages that
// manage their own empty state (SELF_HANDLED_EMPTY) and the project-free
// tabs (NO_PROJECT_TABS) are never walled; every other page is walled when
// the LOCAL projects list is empty. A shared selection is never walled: its
// data does not live in the local list, and the shared read paths carry
// their own loading/empty states (teammate persona: zero local projects,
// drilling from a shared Overview into file/finding/dimension detail).
// Exported so the source-gating contract is unit-testable without mounting
// MainContent's route renderers.
export function shouldWallEmptyProjects({ page, projects, selectedSource }) {
  if (isSharedSource(selectedSource)) return false;
  if (NO_PROJECT_TABS.includes(page) || SELF_HANDLED_EMPTY.has(page)) return false;
  return !projects || projects.length === 0;
}

/**
 * @param {{ activePage: { page: string }, props: Object }} params
 * @returns {JSX.Element|null}
 */
export function MainContent({ activePage, props }) {
  const { page, ...params } = activePage;
  if (shouldWallEmptyProjects({ page, projects: props.navigation?.projects, selectedSource: props.navigation?.selectedSource })) {
    if (!props.navigation?.projectsLoaded) {
      // Mirror of DashboardPage's gate: a failed startup load must offer a
      // retry instead of an unrecoverable fullscreen spinner.
      if (props.navigation?.projectsLoadFailed) {
        return (
          <EmptyState
            title={t('overview.projectsLoadFailedTitle')}
            description={t('overview.projectsLoadFailedDesc')}
            actionLabel={t('overview.retry')}
            onAction={() => props.navigation.retryLoadProjects?.()}
          />
        );
      }
      // The app-level FadingLoadingScreen overlay covers this state; render
      // nothing here so the loader lives at one stable spot and can fade out.
      return null;
    }
    return (
      <EmptyStateWithTour
        onAdd={() => props.navigation.onAddProject()}
        onTour={() => props.navigation.onTakeTour()}
        onBrowseRemote={props.navigation.onBrowseRemote}
        isEvaluating={props.navigation.isEvaluating}
      />
    );
  }
  const renderer = ROUTE_RENDERERS[page];
  if (renderer) return renderer(params, props);
  return null;
}
