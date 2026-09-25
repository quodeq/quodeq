/**
 * Route renderers: the per-route view composition App.jsx's MainContent
 * dispatches to, plus the prop-bundle builders the renderers consume.
 * App state arrives via the explicit `props` bundles — no context. Everything here is exported so
 * the route contracts stay unit-testable without mounting the whole App
 * (which needs ~8 providers).
 */
import { lazy } from 'react';
import EmptyState from '../components/EmptyState.jsx';
import EmptyStateWithTour from '../features/onboarding/components/EmptyStateWithTour.jsx';
import { isSharedSource, findProject, makeDismissHandler } from './dismissWiring.js';
import { t } from '../strings/index.js';
import { buildEvalPrincipal, ViolationsRoute } from './violationsRoute.jsx';
import { mapRoute } from './mapRoute.jsx';
import { historyRoute } from './historyRoute.jsx';
import { compareRoute } from './compareRoute.jsx';
import { buildDashboardDataBundle } from './dashboardDataBundle.js';
import { buildNavigationBundle } from './navigationBundle.js';
import { NAV_TAB } from '../vocab/navTab.js';
import {
  EvaluateCase, SettingsCase, renderEvalPrincipleDetail,
  resolveSelectionAfterSharedDisconnect,
} from './routeCases.jsx';

const DashboardPage = lazy(() => import('../features/dashboard/components/DashboardPage.jsx'));
const ExplorerPage = lazy(() => import('../features/explorer/components/ExplorerPage.jsx'));
const FileDetailPage = lazy(() => import('../features/explorer/components/FileDetailPage.jsx'));
const FindingDetailPage = lazy(() => import('../features/explorer/components/FindingDetailPage.jsx'));
const ProjectsPage = lazy(() => import('../features/dashboard/components/ProjectsPage.jsx'));
const GradeFormulaPage = lazy(() => import('../features/grade-formula/GradeFormulaPage.jsx'));
const StandardsPage = lazy(() => import('../features/standards/StandardsPage.jsx'));
const HelpPage = lazy(() => import('../features/help/components/HelpPage.jsx'));

// The source gate, the project lookup, buildEvalPrincipal,
// buildDashboardDataBundle and buildNavigationBundle are re-exported below
// (their consumers -- App.jsx, this file's own route renderers, and the tests
// that pin producer/consumer contracts -- all import them from here); they
// are defined in sibling modules: dismissWiring.js,
// violationsRoute.jsx, dashboardDataBundle.js and navigationBundle.js.
export { isSharedSource, findProject, makeDismissHandler };
export { buildEvalPrincipal };
export { buildDashboardDataBundle };
export { buildNavigationBundle };
// resolveSelectionAfterSharedDisconnect is defined in routeCases.jsx with the
// Settings route it serves; App.jsx and its tests import it from here.
export { resolveSelectionAfterSharedDisconnect };

// Tabs that are reachable with zero projects. `projects` is in here so a
// fresh-install user can land on Projects and add their first one without
// hitting the "no analyzed projects yet" wall.
const NO_PROJECT_TABS = [
  NAV_TAB.PROJECTS, NAV_TAB.EVALUATE, NAV_TAB.STANDARDS, NAV_TAB.SETTINGS, NAV_TAB.HELP, NAV_TAB.GRADE_FORMULA, NAV_TAB.COMPARE,
];
const SELF_HANDLED_EMPTY = new Set([NAV_TAB.OVERVIEW, NAV_TAB.MAP, NAV_TAB.VIOLATIONS, NAV_TAB.HISTORY]);

/**
 * The dashboard page for a route. Every dashboard route navigates and
 * retries; `callbacks` adds the route's own.
 */
function dashboardElement(props, runMode, callbacks = {}) {
  return (
    <DashboardPage
      data={props.dashboardData}
      callbacks={{ onNavigate: props.navigation.handleNavigate, onRetry: props.dashboardData.onRetry, ...callbacks }}
      runMode={runMode}
    />
  );
}

/**
 * @param {{ serverHealth: Object, evaluation: Object, selectedProject: string, projects: Array, onGoToProjects: Function, onGoToSettings: Function, preselectDims: string[]|undefined }} props
 * @returns {JSX.Element}
 */
// Exported for the same reason as buildEvalPrincipal — a unit-testable pin
// on the per-route onDismiss source-gating contract without mounting the
// whole App (which needs ~8 providers). Calling e.g.
// ROUTE_RENDERERS.file(params, props) just builds the React element tree; it
// doesn't render, so the returned element's props can be asserted on directly.
export const ROUTE_RENDERERS = {
  overview: (params, props) => dashboardElement(props, false, {
    onRunSelect: props.navigation.handleRunSelect,
    onProjectsReload: props.navigation.loadProjects,
    onProjectsRetry: props.dashboardData.onProjectsRetry,
  }),
  violations: (params, props) => <ViolationsRoute params={params} props={props} />,
  map: mapRoute,
  run: (params, props) => dashboardElement(props, true, { onProjectsRetry: props.dashboardData.onProjectsRetry }),
  history: historyRoute,
  [NAV_TAB.HISTORY_RUN]: (params, props) => dashboardElement(props, true),
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
    return (
      <EvaluateCase
        evaluation={props.evaluation}
        selectedProject={props.navigation.selectedProject}
        projects={props.navigation.projects}
        preselectDims={params.preselectDims}
        onGoToProjects={() => props.navigation.navTab(NAV_TAB.PROJECTS)}
        onGoToSettings={() => props.navigation.navTab(NAV_TAB.SETTINGS)}
      />
    );
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
      onDismiss={makeDismissHandler({
        selectedSource: props.navigation.selectedSource,
        runId: params.runId,
        explicitProject: params.fromProject,
        selectedProject: props.navigation.selectedProject,
        deps: props,
      })}
    />
  ),
  [NAV_TAB.EVAL_PRINCIPLE]: renderEvalPrincipleDetail,
  [NAV_TAB.EVAL_PRINCIPLE_DETAIL]: renderEvalPrincipleDetail,
  finding: (params, props) => (
    <FindingDetailPage
      finding={params.finding}
      principle={params.principle}
      dimension={params.dimension}
      // Same identity rule as the file and evalprinciple routes.
      onDismiss={makeDismissHandler({
        selectedSource: props.navigation.selectedSource,
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
    onOpenGradeFormula={() => props.navigation.handleNavigate(NAV_TAB.GRADE_FORMULA)}
    onSharedDisconnected={() => {
      const next = resolveSelectionAfterSharedDisconnect({
        selectedSource: props.navigation.selectedSource,
        projects: props.navigation.projects,
      });
      if (next) props.navigation.handleProjectChange(next.id, next.source);
    }}
  />,
  [NAV_TAB.GRADE_FORMULA]: (params, props) => <GradeFormulaPage navigation={props.navigation} />,
  projects: (params, props) => (
    <ProjectsPage
      projects={props.navigation.projects}
      projectsLoaded={props.navigation.projectsLoaded}
      selectedProject={props.navigation.selectedProject}
      isEvaluating={props.navigation.isEvaluating}
      filters={params.filters}
      actions={{
        onSelect: (id, source) => {
          props.navigation.handleProjectChange(id, source);
          props.navigation.navTab(NAV_TAB.OVERVIEW);
        },
        onDelete: props.navigation.handleDeleteProject,
        onExport: props.navigation.handleExportProject,
        onRelocate: props.navigation.handleRelocateProject,
        onAddProject: props.navigation.onAddProject,
        onImportProject: props.navigation.onImportProject,
        onResumeSetup: props.navigation.onResumeSetup,
        onFiltersChange: (filters) => props.navigation.handleNavigateReplace(NAV_TAB.PROJECTS, { filters }),
        onProjectsReload: props.navigation.loadProjects,
      }}
    />
  ),
  standards: (params, props) => <StandardsPage onRescan={(dims) => props.navigation.navTab(NAV_TAB.EVALUATE, { preselectDims: dims })} />,
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
  console.warn('[renderers] unrecognized route:', page);
  return <EmptyState title={t('overview.routeNotFoundTitle')} description={t('overview.routeNotFoundDesc')} />;
}
