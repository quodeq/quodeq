/**
 * The Violations tab's route renderer, moved out of routes/renderers.jsx
 * verbatim (move-only refactor). onDismiss gating and dismissWithReconcile
 * have regression history -- this file does not touch either (ViolationsPage
 * itself has no onDismiss; dismiss lives on the file/finding/evalprinciple
 * detail routes, which stay in routes/renderers.jsx).
 *
 * ViolationsRoute itself was pulled apart into the helpers below (make...,
 * build...) purely to fit the size ratchet's per-function line cap -- same
 * logic, same closures, just named and factored out instead of inlined.
 */
import { lazy } from 'react';
import { buildProjectRootFile } from '../utils/explorerUtils.js';

const ViolationsPage = lazy(() => import('../features/violations/components/ViolationsPage.jsx'));

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

function makeNavigateToPrinciple({ dimMap, principleMap, nav }) {
  return (principleObj, severity) => {
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
  };
}

function makeNavigateToDimension({ dimMap, nav }) {
  return (row, severity) => {
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
  };
}

function buildViolationsData({ props, acc, dims }) {
  return {
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
  };
}

// ViolationsPage fires onRefresh on EVERY mount (its tabKey effect),
// including plain drill-down/back navigation with no mutation -- the page
// remounts on every round trip. onRefresh must stay wired to the lazy
// refreshDashboard (mark-stale, refetchType:'none') so plain navigation
// never forces an active refetch of the 10-20 MB dashboard payload.
// Restore/delete (single + bulk) route through a SEPARATE onReconcile
// callback via useDismissedFindings, called alongside onRefresh from its
// four mutation handlers. restore-all/delete-all return a payload
// applyMutationDelta can't patch (scores:null, delta.isLatest:false), so
// those need the debounced ACTIVE reconcile -- see scheduleDashboardReconcile
// in useDashboard.js.
function buildViolationsCallbacks({ props, nav, navigateToPrinciple, navigateToDimension }) {
  return {
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
    onRefresh: props.refreshDashboard,
    onReconcile: props.scheduleDashboardReconcile,
    onNavigate: nav,
    onRetry: props.dashboardData.onRetry,
  };
}

function buildViolationsPageProps({ params, props, acc, dims, nav, navigateToPrinciple, navigateToDimension }) {
  return {
    data: buildViolationsData({ props, acc, dims }),
    callbacks: buildViolationsCallbacks({ props, nav, navigateToPrinciple, navigateToDimension }),
    isDirectNav: props.navigation.navStackLength === 1,
    tabKey: params._tabKey || 0,
    // The by-dimension / by-file / dismissed flip is view state on the SAME
    // screen: it lives in the route entry so back/forward and the crumb see
    // it, but flipping replaces (never pushes) so history doesn't grow.
    // Params are spread forward so _tabKey survives the flip.
    subTab: params.subTab || 'dimension',
    onSubTabChange: (v) => props.navigation.handleNavigateReplace('violations', { ...params, subTab: v }),
  };
}

export function ViolationsRoute({ params, props }) {
  const acc = props.dashboardData.latestAccumulated || props.dashboardData.accumulated;
  const dims = acc?.dimensions || [];
  const nav = props.navigation.handleNavigate;

  const dimMap = new Map(dims.map(d => [d.dimension, d]));
  const principleMap = new Map(
    dims.flatMap(d => (d.principles || []).map(p => [`${d.dimension}\0${p.name || p.principle}`, p]))
  );
  const navigateToPrinciple = makeNavigateToPrinciple({ dimMap, principleMap, nav });
  const navigateToDimension = makeNavigateToDimension({ dimMap, nav });

  return (
    <ViolationsPage
      {...buildViolationsPageProps({ params, props, acc, dims, nav, navigateToPrinciple, navigateToDimension })}
    />
  );
}
