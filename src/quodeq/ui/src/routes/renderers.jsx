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
import { t } from '../strings/index.js';
import { buildEvalPrincipal, ViolationsRoute } from './violationsRoute.jsx';
import { mapRoute } from './mapRoute.jsx';
import { historyRoute } from './historyRoute.jsx';
import { compareRoute } from './compareRoute.jsx';
import { buildDashboardDataBundle } from './dashboardDataBundle.js';
import { buildNavigationBundle } from './navigationBundle.js';

const DashboardPage = lazy(() => import('../features/dashboard/components/DashboardPage.jsx'));
const ExplorerPage = lazy(() => import('../features/explorer/components/ExplorerPage.jsx'));
const FileDetailPage = lazy(() => import('../features/explorer/components/FileDetailPage.jsx'));
const PrincipleDetailPage = lazy(() => import('../features/explorer/components/PrincipleDetailPage.jsx'));
const FindingDetailPage = lazy(() => import('../features/explorer/components/FindingDetailPage.jsx'));
const ProjectsPage = lazy(() => import('../features/dashboard/components/ProjectsPage.jsx'));
const EvaluateScreen = lazy(() => import('../features/evaluation/components/EvaluateScreen.jsx'));
const SettingsPage = lazy(() => import('../features/settings/components/SettingsPage.jsx'));
const GradeFormulaPage = lazy(() => import('../features/grade-formula/GradeFormulaPage.jsx'));
const StandardsPage = lazy(() => import('../features/standards/StandardsPage.jsx'));
const HelpPage = lazy(() => import('../features/help/components/HelpPage.jsx'));

// buildEvalPrincipal, buildDashboardDataBundle and buildNavigationBundle are
// re-exported below (their consumers -- App.jsx, this file's own route
// renderers, and the tests that pin producer/consumer contracts -- all
// import them from here) even though they now live in sibling modules; see
// violationsRoute.jsx, dashboardDataBundle.js and navigationBundle.js.
export { buildEvalPrincipal };
export { buildDashboardDataBundle };
export { buildNavigationBundle };

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

// Exported for the same reason as buildEvalPrincipal — a unit-testable pin
// on the per-route onDismiss source-gating contract without mounting the
// whole App (which needs ~8 providers). Calling e.g.
// ROUTE_RENDERERS.file(params, props) just builds the React element tree; it
// doesn't render, so the returned element's props can be asserted on directly.
export const ROUTE_RENDERERS = {
  overview: (params, props) => <DashboardPage data={props.dashboardData} callbacks={{ onNavigate: props.navigation.handleNavigate, onRunSelect: props.navigation.handleRunSelect, onProjectsReload: props.navigation.loadProjects, onRetry: props.dashboardData.onRetry, onProjectsRetry: props.dashboardData.onProjectsRetry }} runMode={false} />,
  violations: (params, props) => <ViolationsRoute params={params} props={props} />,
  map: mapRoute,
  run: (params, props) => <DashboardPage data={props.dashboardData} callbacks={{ onNavigate: props.navigation.handleNavigate, onRetry: props.dashboardData.onRetry, onProjectsRetry: props.dashboardData.onProjectsRetry }} runMode={true} />,
  history: historyRoute,
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
  compare: compareRoute,
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
