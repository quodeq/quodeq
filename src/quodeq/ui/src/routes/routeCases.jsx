/**
 * The three routes whose view composition needs more than a prop spread:
 * Evaluate (which resolves the running job's project), Settings (which owns
 * the shared-disconnect recovery) and the principle detail page (which
 * resolves its finding's own project before wiring up dismiss). Kept beside
 * renderers.jsx rather than in it so the route table stays a table.
 */
import { lazy } from 'react';
import { findProject, makeDismissHandler } from './dismissWiring.js';

const EvaluateScreen = lazy(() => import('../features/evaluation/components/EvaluateScreen.jsx'));
const SettingsPage = lazy(() => import('../features/settings/components/SettingsPage.jsx'));
const PrincipleDetailPage = lazy(() => import('../features/explorer/components/PrincipleDetailPage.jsx'));

/**
 * Evaluate route: splits the evaluation bundle into the three prop groups
 * EvaluateScreen takes, and resolves the project names the screen shows as
 * labels (the global selection, the running job's own project, and the
 * project the job was started for) into full project records.
 * @param {object} props
 * @param {object} props.evaluation - useEvaluation's bundle: the job, its
 *   error, live violations and the start/cancel/dismiss handlers.
 * @param {string} props.selectedProject - the app's global project selection.
 * @param {Array} props.projects - every known project, for the name lookups.
 * @param {() => void} props.onGoToProjects - escape hatch from an empty state.
 * @param {() => void} props.onGoToSettings - escape hatch when no provider is
 *   configured yet.
 * @param {Array} [props.preselectDims] - dimensions to tick on entry.
 * @returns {JSX.Element}
 */
export function EvaluateCase({ evaluation, selectedProject, projects, onGoToProjects, onGoToSettings, preselectDims }) {
  const { job, jobError, liveViolations, handleStartEvaluation, handleEvalDismiss, cancelEvaluation, startedProject } = evaluation;
  const projectInfo = findProject(projects, selectedProject);
  // The in-progress card describes the running job's own project, which can
  // differ from the UI's global selection. Resolve it the same way so the
  // card label follows the job rather than the selection. Before the
  // report-path marker resolves outputProject, the project the job was
  // started for fills the gap; the global selection is never used.
  const jobProjectInfo = job?.outputProject ? findProject(projects, job.outputProject) : null;
  const startedProjectInfo = startedProject ? findProject(projects, startedProject) : null;
  return (
    <EvaluateScreen
      evaluation={{ job, jobError, liveViolations }}
      context={{ selectedProject, projectInfo, jobProjectInfo, startedProjectInfo, preselectDims }}
      actions={{ onStart: handleStartEvaluation, onDismiss: handleEvalDismiss, onCancel: cancelEvaluation, onGoToProjects, onGoToSettings }}
    />
  );
}

/**
 * @param {{ settings: Object }} props
 * @returns {JSX.Element}
 */
export function SettingsCase({ settings, onOpenGradeFormula, onSharedDisconnected }) {
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

/**
 * Principle detail route. The URL params carry the finding, but a jump from
 * Compare or a parent dimension can omit its project and run, so both are
 * backfilled from the current navigation before the page is wired to dismiss.
 * @param {object} params - the parsed route params: `evalPrincipal` and an
 *   optional `severity` filter.
 * @param {object} props - the route props; `props.navigation` supplies the
 *   selection fallbacks and the rest is passed to the dismiss handler.
 * @returns {JSX.Element}
 */
export function renderEvalPrincipleDetail(params, props) {
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
      onDismiss={makeDismissHandler({
        selectedSource,
        fallbackDimension: evalPrincipal.dimension,
        runId: evalPrincipal.runId,
        explicitProject: evalPrincipal.project,
        selectedProject,
        deps: props,
      })}
    />
  );
}
