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
import { NAV_TAB } from '../vocab/navTab.js';
import { ROW_TYPE, VIOLATIONS_SUB_TAB } from '../features/violations/violationsVocab.js';
import { typeFile } from '../features/violations/byTypeModel.js';
import { SEVERITY_FILTER_ALL } from '../vocab/severity.js';
import { FILE_SELECTOR_KIND, buildEvalPrincipal } from './liveSelectors.js';

// buildEvalPrincipal moved to routes/liveSelectors.js (the Principle page
// rebuilds it from the live payload there); re-exported for its tests.
export { buildEvalPrincipal };

const ViolationsPage = lazy(() => import('../features/violations/components/ViolationsPage.jsx'));

function makeNavigateToPrinciple({ dimMap, principleMap, nav }) {
  return (principleObj, severity) => {
    const dim = dimMap.get(principleObj.dimension);
    const pg = principleMap.get(`${principleObj.dimension}\0${principleObj.principle}`);
    // dim.fromRunId is the run whose data populated this accumulated entry;
    // threading it through lets the dismiss POST carry a real run id so the
    // backend can rescore and project the action into SQL — without this the
    // PrincipleDetail score never moves on dismiss and the entry never lands
    // on the Dismissed tab.
    // The selector next to the snapshot lets the page rebuild the principal
    // from the live payload (routes/liveSelectors.js).
    nav(NAV_TAB.EVAL_PRINCIPLE, {
      evalPrincipal: buildEvalPrincipal(principleObj, pg, dim?.fromRunId),
      principleSelector: { dimension: principleObj.dimension, principle: principleObj.principle },
      severity,
      sourceTab: NAV_TAB.VIOLATIONS,
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
    nav(NAV_TAB.FILE, {
      file: dimFile,
      fileSelector: { kind: FILE_SELECTOR_KIND.DIMENSION, dimension: dim.dimension },
      severityFilter,
      runId: dim.fromRunId,
      dateLabel: dim.fromDateLabel,
      sourceTab: NAV_TAB.VIOLATIONS,
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

// ViolationsPage does not refresh on mount. Restore/delete (single + bulk)
// route through onReconcile via useDismissedFindings; restore-all/delete-all
// return a payload applyMutationDelta can't patch (scores:null,
// delta.isLatest:false), so those need the debounced ACTIVE reconcile -- see
// scheduleDashboardReconcile in useDashboard.js.
// A type row drills into the findings of that requirement code alone, as a
// synthetic file built from the dimension's own run (the same mechanism the
// dimension rows use), so the file page needs no new filter.
function makeNavigateToType({ dimMap, nav }) {
  return (row) => {
    const dim = dimMap.get(row.dimension);
    if (!dim) return;
    nav(NAV_TAB.FILE, {
      file: typeFile(row, dim, `${row.req} · ${row.text || dim.dimension}`),
      fileSelector: { kind: FILE_SELECTOR_KIND.TYPE, dimension: row.dimension, req: row.req, text: row.text },
      severityFilter: SEVERITY_FILTER_ALL,
      runId: row.runId,
      dateLabel: row.dateLabel,
      sourceTab: NAV_TAB.VIOLATIONS,
    });
  };
}
function buildViolationsCallbacks({ props, nav, navigateToPrinciple, navigateToDimension, navigateToType }) {
  return {
    onTypeClick: navigateToType,
    onBumpDismissRefresh: props.bumpDismissRefresh,
    onDimensionClick: (dim) => nav(NAV_TAB.EXPLORER, { dimension: dim.dimension, runId: dim.fromRunId, dateLabel: dim.fromDateLabel, fromProject: dim.fromProject, sourceTab: NAV_TAB.VIOLATIONS }),
    onFileClick: (fileObj, opts) => nav(NAV_TAB.FILE, { file: fileObj, sourceTab: NAV_TAB.VIOLATIONS, severityFilter: opts?.severity || null }),
    onCellClick: ({ row, severity }) => {
      if (row.type === ROW_TYPE.PRINCIPLE && row.principleObj) {
        navigateToPrinciple(row.principleObj, severity);
      } else {
        navigateToDimension(row, severity);
      }
    },
    onPrincipleClick: (principleObj) => navigateToPrinciple(principleObj),
    onReconcile: props.scheduleDashboardReconcile,
    onNavigate: nav,
    onRetry: props.dashboardData.onRetry,
  };
}

function buildViolationsPageProps({ params, props, acc, dims, nav, navigateToPrinciple, navigateToDimension, navigateToType }) {
  return {
    data: buildViolationsData({ props, acc, dims }),
    callbacks: buildViolationsCallbacks({ props, nav, navigateToPrinciple, navigateToDimension, navigateToType }),
    tabKey: params._tabKey || 0,
    // The by-dimension / by-file / dismissed flip is view state on the SAME
    // screen: it lives in the route entry so back/forward and the crumb see
    // it, but flipping replaces (never pushes) so history doesn't grow.
    // Params are spread forward so _tabKey survives the flip.
    subTab: params.subTab || VIOLATIONS_SUB_TAB.DIMENSION,
    onSubTabChange: (v) => props.navigation.handleNavigateReplace(NAV_TAB.VIOLATIONS, { ...params, subTab: v }),
  };
}

// dimension -> entry and "dimension\0principle" -> principle lookups for the
// accumulated payload. ViolationsRoute re-renders on every parent state
// change (dismissRefreshKey bumps, sub-tab flips) while `dims` is the same
// react-query array, so rebuilding these each render walked every principle
// for nothing. Memoized by array identity in a WeakMap rather than useMemo:
// ViolationsRoute is deliberately hook-free (the App tests invoke it as a
// plain function), and the entry is released together with its payload.
const LOOKUPS_BY_DIMS = new WeakMap();

export function violationsLookupsFor(dims) {
  let lookups = LOOKUPS_BY_DIMS.get(dims);
  if (!lookups) {
    lookups = {
      dimMap: new Map(dims.map(d => [d.dimension, d])),
      principleMap: new Map(
        dims.flatMap(d => (d.principles || []).map(p => [`${d.dimension}\0${p.name || p.principle}`, p]))
      ),
    };
    LOOKUPS_BY_DIMS.set(dims, lookups);
  }
  return lookups;
}

export function ViolationsRoute({ params, props }) {
  const acc = props.dashboardData.latestAccumulated || props.dashboardData.accumulated;
  const dims = acc?.dimensions || [];
  const nav = props.navigation.handleNavigate;

  const { dimMap, principleMap } = violationsLookupsFor(dims);
  const navigateToPrinciple = makeNavigateToPrinciple({ dimMap, principleMap, nav });
  const navigateToDimension = makeNavigateToDimension({ dimMap, nav });
  const navigateToType = makeNavigateToType({ dimMap, nav });

  return (
    <ViolationsPage
      {...buildViolationsPageProps({ params, props, acc, dims, nav, navigateToPrinciple, navigateToDimension, navigateToType })}
    />
  );
}
